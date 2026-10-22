"""Sample many continuations of one prompt from a Llama model while keeping a single copy of the prompt's key-value cache.

Generating n samples through `generate(num_return_sequences=n)` copies the prompt cache n times and rewrites it every
step; on a CPU that copy dominates the runtime. Here the prompt cache stays at batch size one, and each step computes
attention against it by folding the n samples into the query rows, with a separate small cache for the generated tokens.
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
            logits = model.lm_head(lm.norm(x))[:, -1].float() / temperature
            sorted_logits, sorted_ids = logits.sort(descending=True)
            remove = sorted_logits.softmax(-1).cumsum(-1) > top_p
            remove[:, 1:] = remove[:, :-1].clone()
            remove[:, 0] = False
            sorted_logits[remove] = float("-inf")
            nxt = sorted_ids.gather(1, torch.multinomial(sorted_logits.softmax(-1), 1)).squeeze(1)
            nxt = torch.where(done, torch.full_like(nxt, eos_token_id), nxt)
            generated.append(nxt)
            done |= nxt == eos_token_id
            tokens = nxt[:, None]
            if done.all():
                break
        return torch.stack(generated, 1)
