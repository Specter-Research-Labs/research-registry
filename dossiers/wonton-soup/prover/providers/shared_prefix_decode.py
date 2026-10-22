"""Sample many continuations of one prompt while keeping a single copy of everything computed from the prompt.

Generating n samples through `generate(num_return_sequences=n)` copies the prompt's cache (a decoder-only model's
prompt keys and values, or an encoder-decoder model's encoder output) n times; on a CPU that copying and the per-step
overhead of `generate` dominate the runtime. Here the prompt-derived keys and values stay at batch size one, and each
step attends to them by folding the n samples into the query rows, with a separate small cache for generated tokens.
"""

from typing import Any


def sample_shared_prefix(
    model: Any,
    input_ids: Any,
    num_samples: int,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    eos_token_id: int,
) -> Any:
    import torch
    from transformers import DynamicCache
    from transformers.models.llama.modeling_llama import apply_rotary_pos_emb

    config = model.config
    heads = config.num_attention_heads
    if config.num_key_value_heads != heads:
        raise ValueError("shared-prefix decoding assumes one key-value head per attention head")
    head_dim = config.hidden_size // heads
    n, device, dtype = num_samples, input_ids.device, model.dtype
    lm = model.model

    with torch.no_grad():
        cache = DynamicCache(config=config)
        model(input_ids=input_ids[:, :-1], past_key_values=cache, use_cache=True)
        prefix = [(layer.keys, layer.values) for layer in cache.layers]
        prefix_len = input_ids.shape[1] - 1
        suffix = [
            (
                torch.empty(n, heads, max_new_tokens, head_dim, dtype=dtype, device=device),
                torch.empty(n, heads, max_new_tokens, head_dim, dtype=dtype, device=device),
            )
            for _ in prefix
        ]
        tokens = input_ids[:, -1:].expand(n, 1)
        done = torch.zeros(n, dtype=torch.bool, device=device)
        generated = []
        for step in range(max_new_tokens):
            x = lm.embed_tokens(tokens)
            cos, sin = lm.rotary_emb(x, torch.full((n, 1), prefix_len + step, device=device))
            for layer, (kp, vp), (ks, vs) in zip(lm.layers, prefix, suffix):
                attn = layer.self_attn
                h = layer.input_layernorm(x)
                q = attn.q_proj(h).view(n, 1, heads, head_dim).transpose(1, 2)
                k = attn.k_proj(h).view(n, 1, heads, head_dim).transpose(1, 2)
                v = attn.v_proj(h).view(n, 1, heads, head_dim).transpose(1, 2)
                q, k = apply_rotary_pos_emb(q, k, cos, sin)
                ks[:, :, step : step + 1] = k
                vs[:, :, step : step + 1] = v
                seen = step + 1
                # (1, heads, n, head_dim): the samples become query rows against the single prompt cache.
                q_rows = q.permute(2, 1, 0, 3)
                scores_prefix = torch.matmul(q_rows, kp.transpose(-1, -2)) * attn.scaling
                scores_suffix = torch.matmul(q, ks[:, :, :seen].transpose(-1, -2)) * attn.scaling
                scores = torch.cat([scores_prefix, scores_suffix.permute(2, 1, 0, 3).reshape(1, heads, n, seen)], -1)
                weights = scores.float().softmax(-1).to(dtype)
                out_prefix = torch.matmul(weights[..., :prefix_len], vp)
                w_suffix = weights[..., prefix_len:].permute(2, 1, 0, 3).reshape(n, heads, 1, seen)
                out_suffix = torch.matmul(w_suffix, vs[:, :, :seen]).permute(2, 1, 0, 3).reshape(1, heads, n, head_dim)
                out = (out_prefix + out_suffix).permute(2, 0, 1, 3).reshape(n, 1, heads * head_dim)
                x = x + attn.o_proj(out)
                x = x + layer.mlp(layer.post_attention_layernorm(x))
            logits = model.lm_head(lm.norm(x))[:, -1]
            nxt = _nucleus_sample(logits, temperature, top_p)
            nxt = torch.where(done, torch.full_like(nxt, eos_token_id), nxt)
            generated.append(nxt)
            done |= nxt == eos_token_id
            tokens = nxt[:, None]
            if done.all():
                break
        return torch.stack(generated, 1)


def sample_shared_encoder(
    model: Any,
    input_ids: Any,
    num_samples: int,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> Any:
    """T5 encoder-decoder sampling; finished samples are padded with the pad token, as `generate` does."""
    import torch

    config = model.config
    heads, head_dim = config.num_heads, config.d_kv
    n, device = num_samples, input_ids.device
    decoder = model.decoder
    blocks = decoder.block
    eos, pad = config.eos_token_id, config.pad_token_id

    with torch.no_grad():
        encoded = model.encoder(input_ids=input_ids).last_hidden_state
        cross = [
            (
                block.layer[1].EncDecAttention.k(encoded).view(1, -1, heads, head_dim).transpose(1, 2),
                block.layer[1].EncDecAttention.v(encoded).view(1, -1, heads, head_dim).transpose(1, 2),
            )
            for block in blocks
        ]
        dtype = encoded.dtype
        self_kv = [
            (
                torch.empty(n, heads, max_new_tokens, head_dim, dtype=dtype, device=device),
                torch.empty(n, heads, max_new_tokens, head_dim, dtype=dtype, device=device),
            )
            for _ in blocks
        ]
        bias_attention = blocks[0].layer[0].SelfAttention
        tokens = torch.full((n, 1), config.decoder_start_token_id, dtype=torch.long, device=device)
        done = torch.zeros(n, dtype=torch.bool, device=device)
        generated = []
        for step in range(max_new_tokens):
            seen = step + 1
            position_bias = bias_attention.compute_bias(1, seen, device=device, past_seen_tokens=step)
            x = decoder.embed_tokens(tokens)
            for block, (kc, vc), (ks, vs) in zip(blocks, cross, self_kv):
                attn = block.layer[0].SelfAttention
                h = block.layer[0].layer_norm(x)
                q = attn.q(h).view(n, 1, heads, head_dim).transpose(1, 2)
                ks[:, :, step : step + 1] = attn.k(h).view(n, 1, heads, head_dim).transpose(1, 2)
                vs[:, :, step : step + 1] = attn.v(h).view(n, 1, heads, head_dim).transpose(1, 2)
                scores = torch.matmul(q, ks[:, :, :seen].transpose(-1, -2)) + position_bias
                out = torch.matmul(scores.float().softmax(-1).to(dtype), vs[:, :, :seen])
                x = x + attn.o(out.transpose(1, 2).reshape(n, 1, heads * head_dim))

                cross_attn = block.layer[1].EncDecAttention
                h = block.layer[1].layer_norm(x)
                # (1, heads, n, head_dim): the samples become query rows against the single encoder output.
                q_rows = cross_attn.q(h).view(n, heads, head_dim).transpose(0, 1).unsqueeze(0)
                weights = torch.matmul(q_rows, kc.transpose(-1, -2)).float().softmax(-1).to(dtype)
                out = torch.matmul(weights, vc).squeeze(0).transpose(0, 1).reshape(n, 1, heads * head_dim)
                x = x + cross_attn.o(out)

                x = x + block.layer[2].DenseReluDense(block.layer[2].layer_norm(x))
            x = decoder.final_layer_norm(x)
            if config.scale_decoder_outputs:
                x = x * (config.d_model**-0.5)
            nxt = _nucleus_sample(model.lm_head(x)[:, -1], temperature, top_p)
            nxt = torch.where(done, torch.full_like(nxt, pad), nxt)
            generated.append(nxt)
            done |= nxt == eos
            tokens = nxt[:, None]
            if done.all():
                break
        return torch.stack(generated, 1)


def _nucleus_sample(logits: Any, temperature: float, top_p: float) -> Any:
    import torch

    sorted_logits, sorted_ids = (logits.float() / temperature).sort(descending=True)
    remove = sorted_logits.softmax(-1).cumsum(-1) > top_p
    remove[:, 1:] = remove[:, :-1].clone()
    remove[:, 0] = False
    sorted_logits[remove] = float("-inf")
    return sorted_ids.gather(1, torch.multinomial(sorted_logits.softmax(-1), 1)).squeeze(1)
