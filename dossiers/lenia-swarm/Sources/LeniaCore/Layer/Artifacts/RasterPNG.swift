import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

func writeGrayscalePNG(bytes: Data, width: Int, height: Int, to url: URL) throws {
    let expected = width * height
    guard bytes.count == expected else {
        throw ConfigError.invalidConfig("grayscale PNG stores \(bytes.count) bytes but expected \(expected).")
    }
    guard let provider = CGDataProvider(data: bytes as CFData) else {
        throw ConfigError.invalidConfig("failed to create grayscale PNG data provider.")
    }
    guard let image = CGImage(
        width: width,
        height: height,
        bitsPerComponent: 8,
        bitsPerPixel: 8,
        bytesPerRow: width,
        space: CGColorSpaceCreateDeviceGray(),
        bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
        provider: provider,
        decode: nil,
        shouldInterpolate: false,
        intent: .defaultIntent
    ) else {
        throw ConfigError.invalidConfig("failed to create grayscale PNG image.")
    }
    try finalizePNG(image, to: url)
}

func writeRGBAPNG(rgba: Data, width: Int, height: Int, to url: URL) throws {
    let expected = width * height * 4
    guard rgba.count == expected else {
        throw ConfigError.invalidConfig("RGBA PNG stores \(rgba.count) bytes but expected \(expected).")
    }
    guard let provider = CGDataProvider(data: rgba as CFData) else {
        throw ConfigError.invalidConfig("failed to create RGBA PNG data provider.")
    }
    guard let image = CGImage(
        width: width,
        height: height,
        bitsPerComponent: 8,
        bitsPerPixel: 32,
        bytesPerRow: width * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
        provider: provider,
        decode: nil,
        shouldInterpolate: false,
        intent: .defaultIntent
    ) else {
        throw ConfigError.invalidConfig("failed to create RGBA PNG image.")
    }
    try finalizePNG(image, to: url)
}

private func finalizePNG(_ image: CGImage, to url: URL) throws {
    guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw ConfigError.invalidConfig("failed to create PNG destination.")
    }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else {
        throw ConfigError.invalidConfig("failed to write PNG.")
    }
}
