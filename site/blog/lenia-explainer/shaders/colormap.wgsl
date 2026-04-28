struct RenderConfig {
  sx: u32,
  sy: u32,
  channels: u32,
  _pad: u32,
};

@group(0) @binding(0) var<uniform> config: RenderConfig;
@group(0) @binding(1) var<storage, read> state: array<f32>;
@group(0) @binding(2) var output_texture: texture_storage_2d<rgba8unorm, write>;

const SPECTRUM_COUNT: u32 = 7u;

fn spectrum_color(index: u32) -> vec3<f32> {
  switch index {
    case 0u: { return vec3<f32>(0.0196, 0.0157, 0.0392); }
    case 1u: { return vec3<f32>(0.4863, 0.9608, 1.0); }
    case 2u: { return vec3<f32>(0.3137, 0.4824, 1.0); }
    case 3u: { return vec3<f32>(0.7490, 0.2157, 1.0); }
    case 4u: { return vec3<f32>(1.0, 0.2275, 0.6863); }
    case 5u: { return vec3<f32>(1.0, 0.4431, 0.2196); }
    case 6u: { return vec3<f32>(1.0, 0.8, 0.2706); }
    default: { return vec3<f32>(0.0, 0.0, 0.0); }
  }
}

@compute @workgroup_size(8, 8)
fn render(@builtin(global_invocation_id) gid: vec3<u32>) {
  let x = gid.x;
  let y = gid.y;
  if x >= config.sx || y >= config.sy { return; }

  var total: f32 = 0.0;
  for (var ch = 0u; ch < config.channels; ch++) {
    total += state[(y * config.sx + x) * config.channels + ch];
  }
  total = clamp(total, 0.0, 1.0);

  let corrected = pow(total, 0.88);
  let scaled = corrected * f32(SPECTRUM_COUNT - 1u);
  let lower = u32(floor(scaled));
  let upper = min(lower + 1u, SPECTRUM_COUNT - 1u);
  let blend = scaled - f32(lower);

  let c0 = spectrum_color(lower);
  let c1 = spectrum_color(upper);
  let color = mix(c0, c1, blend);

  textureStore(output_texture, vec2<i32>(i32(x), i32(y)), vec4<f32>(color, 1.0));
}
