#include <metal_stdlib>
#include <SwiftUI/SwiftUI_Metal.h>
using namespace metal;

// Color pipeline operates in linear light. Palettes return linear-sRGB, get
// composited and lit in linear, then encoded to sRGB once at the output. This
// keeps gradients perceptually even and stops mid-tones from muddying the way
// a naive sRGB lerp does.

float3 srgbToLinear(float3 c) {
    float3 lo = c / 12.92;
    float3 hi = pow((c + 0.055) / 1.055, float3(2.4));
    return select(hi, lo, c <= 0.04045);
}

float3 linearToSrgb(float3 c) {
    c = clamp(c, 0.0, 1.0);
    float3 lo = c * 12.92;
    float3 hi = 1.055 * pow(c, float3(1.0 / 2.4)) - 0.055;
    return select(hi, lo, c <= 0.0031308);
}

float3 linearSrgbToOklab(float3 c) {
    float l = 0.4122214708 * c.r + 0.5363325363 * c.g + 0.0514459929 * c.b;
    float m = 0.2119034982 * c.r + 0.6806995451 * c.g + 0.1073969566 * c.b;
    float s = 0.0883024619 * c.r + 0.2817188376 * c.g + 0.6299787005 * c.b;
    float l_ = pow(max(l, 0.0), 1.0 / 3.0);
    float m_ = pow(max(m, 0.0), 1.0 / 3.0);
    float s_ = pow(max(s, 0.0), 1.0 / 3.0);
    return float3(
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_);
}

float3 oklabToLinearSrgb(float3 lab) {
    float l_ = lab.x + 0.3963377774 * lab.y + 0.2158037573 * lab.z;
    float m_ = lab.x - 0.1055613458 * lab.y - 0.0638541728 * lab.z;
    float s_ = lab.x - 0.0894841775 * lab.y - 1.2914855480 * lab.z;
    float l = l_ * l_ * l_;
    float m = m_ * m_ * m_;
    float s = s_ * s_ * s_;
    return float3(
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s);
}

// Interpolate two sRGB stops through OkLab, returning a linear-sRGB color.
float3 mixStopsLab(float3 srgbA, float3 srgbB, float t) {
    float3 a = linearSrgbToOklab(srgbToLinear(srgbA));
    float3 b = linearSrgbToOklab(srgbToLinear(srgbB));
    return oklabToLinearSrgb(mix(a, b, clamp(t, 0.0, 1.0)));
}

// Five sRGB control points interpolated in OkLab. Returns linear-sRGB.
float3 palette5(float t, float3 s0, float3 s1, float3 s2, float3 s3, float3 s4) {
    t = clamp(t, 0.0, 1.0);
    if (t < 0.25) return mixStopsLab(s0, s1, t * 4.0);
    if (t < 0.50) return mixStopsLab(s1, s2, (t - 0.25) * 4.0);
    if (t < 0.75) return mixStopsLab(s2, s3, (t - 0.50) * 4.0);
    return mixStopsLab(s3, s4, (t - 0.75) * 4.0);
}

float3 magma(float t) {
    return palette5(t,
        float3(0.001, 0.000, 0.014),
        float3(0.281, 0.100, 0.422),
        float3(0.711, 0.220, 0.390),
        float3(0.950, 0.550, 0.250),
        float3(0.988, 0.945, 0.750));
}

float3 viridis(float t) {
    return palette5(t,
        float3(0.267, 0.004, 0.329),
        float3(0.282, 0.140, 0.458),
        float3(0.127, 0.566, 0.551),
        float3(0.544, 0.774, 0.247),
        float3(0.993, 0.906, 0.144));
}

float3 inferno(float t) {
    return palette5(t,
        float3(0.001, 0.000, 0.014),
        float3(0.341, 0.062, 0.429),
        float3(0.735, 0.216, 0.330),
        float3(0.978, 0.557, 0.035),
        float3(0.988, 0.998, 0.645));
}

float3 plasma(float t) {
    return palette5(t,
        float3(0.050, 0.030, 0.528),
        float3(0.494, 0.012, 0.658),
        float3(0.798, 0.233, 0.370),
        float3(0.973, 0.585, 0.120),
        float3(0.940, 0.975, 0.131));
}

// Turbo (Mikhailov 2019), the perceptual rainbow Lenia adopted in place of Jet.
// Polynomial fit returns sRGB; convert to linear for the pipeline.
float3 turbo(float t) {
    t = clamp(t, 0.0, 1.0);
    const float4 kR4 = float4(0.13572138, 4.61539260, -42.66032258, 132.13108234);
    const float4 kG4 = float4(0.09140261, 2.19418839, 4.84296658, -14.18503333);
    const float4 kB4 = float4(0.10667330, 12.64194608, -60.58204836, 110.36276771);
    const float2 kR2 = float2(-152.94239396, 59.28637943);
    const float2 kG2 = float2(4.27729857, 2.82956604);
    const float2 kB2 = float2(-89.90310912, 27.34824973);
    float4 v4 = float4(1.0, t, t * t, t * t * t);
    float2 v2 = v4.zw * v4.z;
    float3 srgb = float3(
        dot(v4, kR4) + dot(v2, kR2),
        dot(v4, kG4) + dot(v2, kG2),
        dot(v4, kB4) + dot(v2, kB2));
    return srgbToLinear(clamp(srgb, 0.0, 1.0));
}

// Paul Tol's smooth rainbow, recommended by Chan to expose internal 3D state
// structure where a single-hue ramp washes it out. Stops in sRGB, OkLab-mixed.
float3 tol(float t) {
    return palette5(t,
        float3(0.302, 0.102, 0.541),
        float3(0.133, 0.392, 0.804),
        float3(0.235, 0.722, 0.541),
        float3(0.925, 0.843, 0.224),
        float3(0.792, 0.165, 0.149));
}

float3 bodyColorLinear(float mass) {
    float density = pow(clamp(mass, 0.0, 1.0), 0.42);
    float3 low = float3(0.035, 0.080, 0.095);
    float3 mid = float3(0.125, 0.360, 0.340);
    float3 high = float3(0.900, 0.940, 0.780);
    float3 body = mixStopsLab(low, mid, smoothstep(0.0, 0.38, density));
    body = mix(body, mixStopsLab(low, high, 1.0), smoothstep(0.38, 1.0, density));
    return body;
}

// Tone map raw mass into the [0,1] colormap domain. Matches the offline
// log1p normalization conceptually but the field arrives pre-normalized here.
float toneMass(float mass) {
    float cleaned = smoothstep(0.02, 0.08, mass) * mass;
    return clamp(pow(cleaned, 0.85) * 1.15, 0.0, 1.0);
}

half4 applyLeniaColormap(half4 color, float3 (*cmap)(float)) {
    float mass = float(color.r);
    float3 rgb = cmap(toneMass(mass));
    float glow = smoothstep(0.4, 0.9, mass) * 0.15;
    rgb += glow;
    float alpha = smoothstep(0.01, 0.12, mass);
    return half4(half3(linearToSrgb(rgb)), half(alpha));
}

half4 bodyLeniaColor(float mass) {
    float presence = smoothstep(0.001, 0.035, mass);
    float3 rgb = bodyColorLinear(mass) * presence;
    rgb += srgbToLinear(float3(0.090, 0.060, 0.025)) * smoothstep(0.55, 0.95, mass);
    return half4(half3(linearToSrgb(rgb)), half(presence));
}

[[ stitchable ]] half4 bodyLenia(float2 position, half4 color) {
    return bodyLeniaColor(float(color.r));
}

[[ stitchable ]] half4 smoothLenia(float2 position, half4 color) {
    return applyLeniaColormap(color, magma);
}

[[ stitchable ]] half4 viridisLenia(float2 position, half4 color) {
    return applyLeniaColormap(color, viridis);
}

[[ stitchable ]] half4 infernoLenia(float2 position, half4 color) {
    return applyLeniaColormap(color, inferno);
}

[[ stitchable ]] half4 plasmaLenia(float2 position, half4 color) {
    return applyLeniaColormap(color, plasma);
}

[[ stitchable ]] half4 turboLenia(float2 position, half4 color) {
    return applyLeniaColormap(color, turbo);
}

[[ stitchable ]] half4 tolLenia(float2 position, half4 color) {
    return applyLeniaColormap(color, tol);
}

struct LabStageVertex {
    float2 position;
    float2 texCoord;
};

struct LabStageVarying {
    float4 position [[position]];
    float2 texCoord;
};

struct LabStageUniforms {
    uint renderMode;
    uint channelCount;
    float2 gridSize;
    float lightStrength;
    float rimStrength;
};

// Each channel renders as a translucent pigment, composited additively in
// linear light (channels are emissive contributions, the way Chan maps the
// first channels to R/G/B). Hues are chosen to read apart and mix cleanly.
float3 channelPigment(uint channel) {
    switch (channel) {
        case 0: return srgbToLinear(float3(0.15, 0.85, 0.65));
        case 1: return srgbToLinear(float3(1.00, 0.45, 0.25));
        case 2: return srgbToLinear(float3(0.45, 0.40, 1.00));
        default: return srgbToLinear(float3(0.95, 0.80, 0.25));
    }
}

float maskedMass(float4 sample, uint channelCount) {
    float mass = sample.r;
    if (channelCount >= 2) mass += sample.g;
    if (channelCount >= 3) mass += sample.b;
    if (channelCount >= 4) mass += sample.a;
    return mass;
}

vertex LabStageVarying labStageVertex(
    uint vertexID [[vertex_id]],
    constant LabStageVertex *vertices [[buffer(0)]]
) {
    LabStageVarying out;
    out.position = float4(vertices[vertexID].position, 0.0, 1.0);
    out.texCoord = vertices[vertexID].texCoord;
    return out;
}

// Catmull-Rom weight. The Lenia field is band-limited, so cubic reconstruction
// recovers real sub-cell detail rather than inventing it.
float catmullRom(float x) {
    x = abs(x);
    if (x < 1.0) return 1.5 * x * x * x - 2.5 * x * x + 1.0;
    if (x < 2.0) return -0.5 * x * x * x + 2.5 * x * x - 4.0 * x + 2.0;
    return 0.0;
}

float4 sampleFieldBicubic(
    texture2d<float> tex,
    sampler samp,
    float2 uv,
    float2 gridSize
) {
    float2 coord = uv * gridSize - 0.5;
    float2 base = floor(coord);
    float2 frac = coord - base;
    float4 result = float4(0.0);
    for (int m = -1; m <= 2; m++) {
        float wy = catmullRom(float(m) - frac.y);
        for (int n = -1; n <= 2; n++) {
            float wx = catmullRom(float(n) - frac.x);
            float2 samplePos = (base + float2(float(n), float(m)) + 0.5) / gridSize;
            result += wx * wy * tex.sample(samp, samplePos);
        }
    }
    return result;
}

float sampleMass(
    texture2d<float> tex,
    sampler samp,
    float2 uv,
    float2 gridSize,
    uint channelCount
) {
    return maskedMass(sampleFieldBicubic(tex, samp, uv, gridSize), channelCount);
}

fragment half4 labStageFragment(
    LabStageVarying in [[stage_in]],
    texture2d<float> fieldTexture [[texture(0)]],
    sampler fieldSampler [[sampler(0)]],
    constant LabStageUniforms &uniforms [[buffer(1)]]
) {
    // Field is stored transposed relative to screen, hence the swap.
    float2 uv = float2(in.texCoord.y, in.texCoord.x);
    float2 gridSize = max(uniforms.gridSize, float2(1.0));
    uint channelCount = max(uniforms.channelCount, 1u);

    float4 channels = sampleFieldBicubic(fieldTexture, fieldSampler, uv, gridSize);
    float mass = maskedMass(channels, channelCount);

    if (uniforms.renderMode == 0) {
        float alpha = smoothstep(0.01, 0.12, mass);
        return half4(half3(mass), half(alpha));
    }

    float3 baseColor;
    if (channelCount > 1) {
        // Composite channels as additive pigments, then tone by total mass so
        // brightness tracks density while hue tracks channel composition.
        float3 pigment = channels.r * channelPigment(0);
        if (channelCount >= 2) pigment += channels.g * channelPigment(1);
        if (channelCount >= 3) pigment += channels.b * channelPigment(2);
        if (channelCount >= 4) pigment += channels.a * channelPigment(3);
        float norm = mass > 1e-5 ? toneMass(mass) / mass : 0.0;
        baseColor = pigment * norm;
    } else {
        switch (uniforms.renderMode) {
            case 1: baseColor = bodyColorLinear(mass); break;
            case 2: baseColor = magma(toneMass(mass)); break;
            case 3: baseColor = viridis(toneMass(mass)); break;
            case 4: baseColor = inferno(toneMass(mass)); break;
            case 5: baseColor = plasma(toneMass(mass)); break;
            case 6: baseColor = turbo(toneMass(mass)); break;
            case 9: {
                // Flow: direction -> hue via an OkLCh color wheel, speed ->
                // chroma + brightness, over a dim body substrate. channels.b/.a
                // carry the flow components (dx, dy), pre-scaled to ~[-1,1].
                float2 flow = float2(channels.b, channels.a);
                float speedVis = pow(clamp(length(flow), 0.0, 1.0), 0.55);
                float angle = atan2(flow.y, flow.x);
                float chroma = 0.22 * speedVis;
                float lightness = 0.62 + 0.18 * speedVis;
                float3 wheel = oklabToLinearSrgb(float3(lightness, chroma * cos(angle), chroma * sin(angle)));
                float3 substrate = bodyColorLinear(mass) * 0.30;
                baseColor = mix(substrate, wheel, clamp(speedVis * 2.2, 0.0, 1.0));
                break;
            }
            case 8: baseColor = tol(toneMass(mass)); break;
            case 7: {
                // Flux: tint the body by rate of change. channels.g carries the
                // signed mass delta vs the previous frame; warm = growing
                // (leading edge), cool = receding (trailing edge).
                float3 base = bodyColorLinear(mass);
                float delta = channels.g;
                float3 warm = srgbToLinear(float3(1.00, 0.42, 0.12));
                float3 cool = srgbToLinear(float3(0.16, 0.55, 1.00));
                float3 tint = delta >= 0.0 ? warm : cool;
                float strength = clamp(abs(delta) * 6.0, 0.0, 1.0);
                baseColor = mix(base, tint, strength);
                break;
            }
            default: baseColor = float3(toneMass(mass)); break;
        }
    }

    // Treat total mass as a height field. The gradient gives a surface normal,
    // which turns the flat heatmap into a lit, translucent body.
    float2 texel = 1.0 / gridSize;
    float mx0 = sampleMass(fieldTexture, fieldSampler, uv - float2(texel.x, 0.0), gridSize, channelCount);
    float mx1 = sampleMass(fieldTexture, fieldSampler, uv + float2(texel.x, 0.0), gridSize, channelCount);
    float my0 = sampleMass(fieldTexture, fieldSampler, uv - float2(0.0, texel.y), gridSize, channelCount);
    float my1 = sampleMass(fieldTexture, fieldSampler, uv + float2(0.0, texel.y), gridSize, channelCount);

    const float normalStrength = 6.0;
    float3 normal = normalize(float3(-(mx1 - mx0) * normalStrength,
                                     -(my1 - my0) * normalStrength,
                                     1.0));
    float3 lightDir = normalize(float3(-0.4, -0.55, 0.75));
    float diffuse = clamp(dot(normal, lightDir), 0.0, 1.0);
    float ambient = 0.55;
    float3 lit = baseColor * (ambient + uniforms.lightStrength * diffuse);

    // Fade faint cells to dark so the creature emerges from black instead of
    // showing the colormap's low-end floor (which speckles the background).
    float presence = smoothstep(0.012, 0.10, mass);

    // Fresnel rim: grazing angles glow. Lift toward white so it reads as a
    // translucent-membrane highlight rather than intensifying the body hue.
    float fresnel = pow(1.0 - clamp(normal.z, 0.0, 1.0), 3.0);
    lit += uniforms.rimStrength * fresnel * presence * mix(baseColor, float3(1.0), 0.6);

    lit *= presence;
    float alpha = smoothstep(0.01, 0.12, mass);
    return half4(half3(linearToSrgb(lit)), half(alpha));
}
