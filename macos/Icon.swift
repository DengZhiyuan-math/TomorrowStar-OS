import AppKit

let folder = CommandLine.arguments[1]
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
                                      bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                      isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
        let edge = CGFloat(pixels)
        let rect = NSRect(x: edge * 0.07, y: edge * 0.07, width: edge * 0.86, height: edge * 0.86)
        NSColor(calibratedRed: 0.12, green: 0.20, blue: 0.20, alpha: 1).setFill()
        NSBezierPath(roundedRect: rect, xRadius: edge * 0.20, yRadius: edge * 0.20).fill()
        let star = NSImage(systemSymbolName: "sparkles", accessibilityDescription: nil)!
        let tinted = NSImage(size: NSSize(width: edge, height: edge))
        tinted.lockFocus()
        star.draw(in: NSRect(x: 0, y: 0, width: edge, height: edge))
        NSColor(calibratedRed: 0.86, green: 0.95, blue: 0.69, alpha: 1).setFill()
        NSRect(x: 0, y: 0, width: edge, height: edge).fill(using: .sourceAtop)
        tinted.unlockFocus()
        tinted.draw(in: NSRect(x: edge * 0.22, y: edge * 0.22, width: edge * 0.56, height: edge * 0.56))
        NSGraphicsContext.restoreGraphicsState()
        let suffix = scale == 2 ? "@2x" : ""
        let output = URL(fileURLWithPath: folder).appendingPathComponent("icon_\(size)x\(size)\(suffix).png")
        try bitmap.representation(using: .png, properties: [:])!.write(to: output)
    }
}
