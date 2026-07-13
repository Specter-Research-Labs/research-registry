struct Config {
  sx: u32,
  sy: u32,
  channels: u32,
  nbK: u32,
  dt: f32,
  dd: i32,
  sigma: f32,
  n_param: i32,
  thetaA: f32,
  border: u32,
  kernelRadius: i32,
  _pad: u32,
};

@group(0) @binding(0) var<uniform> config: Config;
@group(0) @binding(1) var<storage, read> state_in: array<f32>;
@group(0) @binding(2) var<storage, read_write> state_out: array<f32>;
@group(0) @binding(3) var<storage, read> kernels: array<f32>;
@group(0) @binding(4) var<storage, read> growth_params: array<f32>;
@group(0) @binding(5) var<storage, read> c0_map: array<u32>;
@group(0) @binding(6) var<storage, read> c1_mask: array<f32>;
@group(0) @binding(7) var<storage, read_write> flow_field: array<f32>;

fn wrap_coord(v: i32, size: u32, is_torus: bool) -> i32 {
  if is_torus {
    return ((v % i32(size)) + i32(size)) % i32(size);
  }
  return clamp(v, 0, i32(size) - 1);
}

fn state_idx(x: u32, y: u32, ch: u32) -> u32 {
  return (y * config.sx + x) * config.channels + ch;
}

fn kernel_idx(kx: u32, ky: u32, k: u32) -> u32 {
  return (ky * config.sx + kx) * config.nbK + k;
}

fn read_state(x: i32, y: i32, ch: u32) -> f32 {
  let is_torus = config.border == 1u;
  let wx = wrap_coord(x, config.sx, is_torus);
  let wy = wrap_coord(y, config.sy, is_torus);
  return state_in[state_idx(u32(wx), u32(wy), ch)];
}

// Classical (non-Flow) Lenia: convolve each kernel with its source channel,
// apply its growth curve, then take an Euler step. The Orbium example uses
// this entry point; Flow Lenia uses the three stages below.
@compute @workgroup_size(8, 8)
fn compute_basic(@builtin(global_invocation_id) gid: vec3<u32>) {
  let x = gid.x;
  let y = gid.y;
  if x >= config.sx || y >= config.sy { return; }

  let midX = i32(config.sx) / 2;
  let midY = i32(config.sy) / 2;
  let kRadius = config.kernelRadius;

  for (var ch = 0u; ch < config.channels; ch++) {
    var growth: f32 = 0.0;
    for (var k = 0u; k < config.nbK; k++) {
      if c1_mask[ch * config.nbK + k] == 0.0 { continue; }
      let c0 = c0_map[k];
      var U_k: f32 = 0.0;
      for (var ky = -kRadius; ky <= kRadius; ky++) {
        for (var kx = -kRadius; kx <= kRadius; kx++) {
          let w = kernels[kernel_idx(u32(kx + midX), u32(ky + midY), k)];
          if abs(w) < 1e-10 { continue; }
          U_k += read_state(i32(x) + kx, i32(y) + ky, c0) * w;
        }
      }
      let m_k = growth_params[k * 4u + 0u];
      let s_k = growth_params[k * 4u + 1u];
      let h_k = growth_params[k * 4u + 2u];
      let diff = (U_k - m_k) / s_k;
      growth += (2.0 * exp(-(diff * diff) / 2.0) - 1.0) * h_k;
    }
    let index = state_idx(x, y, ch);
    state_out[index] = clamp(state_in[index] + config.dt * growth, 0.0, 1.0);
  }
}

@compute @workgroup_size(8, 8)
fn compute_growth(@builtin(global_invocation_id) gid: vec3<u32>) {
  let x = gid.x;
  let y = gid.y;
  if x >= config.sx || y >= config.sy { return; }

  let midX = i32(config.sx) / 2;
  let midY = i32(config.sy) / 2;
  let kRadius = config.kernelRadius;

  for (var k = 0u; k < config.nbK; k++) {
    let c0 = c0_map[k];
    var U_k: f32 = 0.0;

    for (var ky = -kRadius; ky <= kRadius; ky++) {
      for (var kx = -kRadius; kx <= kRadius; kx++) {
        let kernelX = u32(kx + midX);
        let kernelY = u32(ky + midY);
        let w = kernels[kernel_idx(kernelX, kernelY, k)];
        if abs(w) < 1e-10 { continue; }
        let sx_i = i32(x) + kx;
        let sy_i = i32(y) + ky;
        let val = read_state(sx_i, sy_i, c0);
        U_k += val * w;
      }
    }

    let m_k = growth_params[k * 4u + 0u];
    let s_k = growth_params[k * 4u + 1u];
    let h_k = growth_params[k * 4u + 2u];
    let diff = (U_k - m_k) / s_k;
    let bell = exp(-(diff * diff) / 2.0);
    let G_k = (2.0 * bell - 1.0) * h_k;

    for (var ch = 0u; ch < config.channels; ch++) {
      let mask = c1_mask[ch * config.nbK + k];
      if mask > 0.0 {
        let base = (y * config.sx + x) * config.channels + ch;
        state_out[base] += G_k * mask;
      }
    }
  }
}

@compute @workgroup_size(8, 8)
fn compute_flow(@builtin(global_invocation_id) gid: vec3<u32>) {
  let x = gid.x;
  let y = gid.y;
  if x >= config.sx || y >= config.sy { return; }

  let mass = compute_mass(x, y);
  let thetaA = config.thetaA;
  let nf = f32(config.n_param);

  for (var ch = 0u; ch < config.channels; ch++) {
    let alpha_raw = pow(mass / thetaA, nf);
    let alpha = clamp(alpha_raw, 0.0, 1.0);

    let nabla_U = sobel_at(x, y, ch, true);
    let nabla_A = sobel_mass_at(x, y);

    let flow_base = ((y * config.sx + x) * config.channels + ch) * 2u;
    flow_field[flow_base + 0u] = (1.0 - alpha) * nabla_U.x - alpha * nabla_A.x;
    flow_field[flow_base + 1u] = (1.0 - alpha) * nabla_U.y - alpha * nabla_A.y;

    // `state_out` still holds the growth field here. Reintegrate overwrites it
    // after every invocation has sampled that field; clearing it here races
    // neighboring Sobel reads and collapses the velocity field.
  }
}

fn compute_mass(x: u32, y: u32) -> f32 {
  var total: f32 = 0.0;
  for (var ch = 0u; ch < config.channels; ch++) {
    total += state_in[state_idx(x, y, ch)];
  }
  return total;
}

fn sobel_at(x: u32, y: u32, ch: u32, use_growth: bool) -> vec2<f32> {
  let ix = i32(x);
  let iy = i32(y);
  var a00: f32; var a01: f32; var a02: f32;
  var a10: f32; var a12: f32;
  var a20: f32; var a21: f32; var a22: f32;

  if use_growth {
    a00 = read_growth(ix - 1, iy - 1, ch);
    a01 = read_growth(ix, iy - 1, ch);
    a02 = read_growth(ix + 1, iy - 1, ch);
    a10 = read_growth(ix - 1, iy, ch);
    a12 = read_growth(ix + 1, iy, ch);
    a20 = read_growth(ix - 1, iy + 1, ch);
    a21 = read_growth(ix, iy + 1, ch);
    a22 = read_growth(ix + 1, iy + 1, ch);
  } else {
    a00 = read_state(ix - 1, iy - 1, ch);
    a01 = read_state(ix, iy - 1, ch);
    a02 = read_state(ix + 1, iy - 1, ch);
    a10 = read_state(ix - 1, iy, ch);
    a12 = read_state(ix + 1, iy, ch);
    a20 = read_state(ix - 1, iy + 1, ch);
    a21 = read_state(ix, iy + 1, ch);
    a22 = read_state(ix + 1, iy + 1, ch);
  }

  let gx = (a00 + 2.0 * a10 + a20) - (a02 + 2.0 * a12 + a22);
  let gy = (a00 + 2.0 * a01 + a02) - (a20 + 2.0 * a21 + a22);
  return vec2<f32>(gy, gx);
}

fn read_growth(x: i32, y: i32, ch: u32) -> f32 {
  let is_torus = config.border == 1u;
  let wx = wrap_coord(x, config.sx, is_torus);
  let wy = wrap_coord(y, config.sy, is_torus);
  return state_out[(u32(wy) * config.sx + u32(wx)) * config.channels + ch];
}

fn sobel_mass_at(x: u32, y: u32) -> vec2<f32> {
  let ix = i32(x);
  let iy = i32(y);
  let a00 = read_mass(ix - 1, iy - 1);
  let a01 = read_mass(ix, iy - 1);
  let a02 = read_mass(ix + 1, iy - 1);
  let a10 = read_mass(ix - 1, iy);
  let a12 = read_mass(ix + 1, iy);
  let a20 = read_mass(ix - 1, iy + 1);
  let a21 = read_mass(ix, iy + 1);
  let a22 = read_mass(ix + 1, iy + 1);

  let gx = (a00 + 2.0 * a10 + a20) - (a02 + 2.0 * a12 + a22);
  let gy = (a00 + 2.0 * a01 + a02) - (a20 + 2.0 * a21 + a22);
  return vec2<f32>(gy, gx);
}

fn read_mass(x: i32, y: i32) -> f32 {
  let is_torus = config.border == 1u;
  let wx = wrap_coord(x, config.sx, is_torus);
  let wy = wrap_coord(y, config.sy, is_torus);
  var total: f32 = 0.0;
  for (var ch = 0u; ch < config.channels; ch++) {
    total += state_in[state_idx(u32(wx), u32(wy), ch)];
  }
  return total;
}

@compute @workgroup_size(8, 8)
fn reintegrate(@builtin(global_invocation_id) gid: vec3<u32>) {
  let x = gid.x;
  let y = gid.y;
  if x >= config.sx || y >= config.sy { return; }

  let is_torus = config.border == 1u;
  let dd = config.dd;
  let sigma = config.sigma;
  let dt = config.dt;
  let ma = f32(dd) - sigma;
  let clipMax = min(1.0, 2.0 * sigma);
  let areaScale = 1.0 / (4.0 * sigma * sigma);

  let posX = f32(x) + 0.5;
  let posY = f32(y) + 0.5;

  for (var ch = 0u; ch < config.channels; ch++) {
    var accum: f32 = 0.0;

    for (var dx = -dd; dx <= dd; dx++) {
      for (var dy = -dd; dy <= dd; dy++) {
        let nx = wrap_coord(i32(x) + dx, config.sx, is_torus);
        let ny = wrap_coord(i32(y) + dy, config.sy, is_torus);
        let nux = u32(nx);
        let nuy = u32(ny);

        let A_r = state_in[state_idx(nux, nuy, ch)];
        let flow_base = ((nuy * config.sx + nux) * config.channels + ch) * 2u;
        let fx = flow_field[flow_base + 0u];
        let fy = flow_field[flow_base + 1u];

        let neighborPosX = f32(nx) + 0.5;
        let neighborPosY = f32(ny) + 0.5;
        var murX = neighborPosX + clamp(dt * fx, -ma, ma);
        var murY = neighborPosY + clamp(dt * fy, -ma, ma);

        if !is_torus {
          murX = clamp(murX, sigma, f32(config.sx) - sigma);
          murY = clamp(murY, sigma, f32(config.sy) - sigma);
        }

        var dMinX = abs(posX - murX);
        var dMinY = abs(posY - murY);

        if is_torus {
          dMinX = min(dMinX, f32(config.sx) - dMinX);
          dMinY = min(dMinY, f32(config.sy) - dMinY);
        }

        let szX = clamp(0.5 - dMinX + sigma, 0.0, clipMax);
        let szY = clamp(0.5 - dMinY + sigma, 0.0, clipMax);
        let area = szX * szY;

        accum += A_r * area;
      }
    }

    state_out[state_idx(x, y, ch)] = accum * areaScale;
  }
}
