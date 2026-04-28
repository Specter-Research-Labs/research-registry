#include <metal_stdlib>
#include <SwiftUI/SwiftUI_Metal.h>
using namespace metal;

float3 palette5(float t, float3 s0, float3 s1, float3 s2, float3 s3, float3 s4) {
    t = clamp(t, 0.0, 1.0);
    if (t < 0.25) return mix(s0, s1, t * 4.0);
    if (t < 0.50) return mix(s1, s2, (t - 0.25) * 4.0);
    if (t < 0.75) return mix(s2, s3, (t - 0.50) * 4.0);
    return mix(s3, s4, (t - 0.75) * 4.0);
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

half4 applyLeniaColormap(half4 color, float3 (*cmap)(float)) {
    float mass = float(color.r);
    float cleaned = smoothstep(0.02, 0.08, mass) * mass;
    float contrasted = pow(cleaned, 0.85);
    float boosted = clamp(contrasted * 1.15, 0.0, 1.0);
    float3 rgb = cmap(boosted);
    float alpha = smoothstep(0.01, 0.12, mass);
    float glow = smoothstep(0.4, 0.9, mass) * 0.15;
    rgb = rgb + glow;
    return half4(half3(rgb), half(alpha));
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
};

vertex LabStageVarying labStageVertex(
    uint vertexID [[vertex_id]],
    constant LabStageVertex *vertices [[buffer(0)]]
) {
    LabStageVarying out;
    out.position = float4(vertices[vertexID].position, 0.0, 1.0);
    out.texCoord = vertices[vertexID].texCoord;
    return out;
}

fragment half4 labStageFragment(
    LabStageVarying in [[stage_in]],
    texture2d<float> fieldTexture [[texture(0)]],
    sampler fieldSampler [[sampler(0)]],
    constant LabStageUniforms &uniforms [[buffer(1)]]
) {
    float mass = fieldTexture.sample(fieldSampler, float2(in.texCoord.y, in.texCoord.x)).r;
    if (uniforms.renderMode == 0) {
        float alpha = smoothstep(0.01, 0.12, mass);
        return half4(half3(mass), half(alpha));
    }

    float cleaned = smoothstep(0.02, 0.08, mass) * mass;
    float contrasted = pow(cleaned, 0.85);
    float boosted = clamp(contrasted * 1.15, 0.0, 1.0);

    float3 rgb;
    switch (uniforms.renderMode) {
        case 1:
            rgb = magma(boosted);
            break;
        case 2:
            rgb = viridis(boosted);
            break;
        case 3:
            rgb = inferno(boosted);
            break;
        case 4:
            rgb = plasma(boosted);
            break;
        default:
            rgb = float3(boosted, boosted, boosted);
            break;
    }

    float alpha = smoothstep(0.01, 0.12, mass);
    float glow = smoothstep(0.4, 0.9, mass) * 0.15;
    rgb = rgb + glow;
    return half4(half3(rgb), half(alpha));
}
