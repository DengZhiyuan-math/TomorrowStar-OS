import Foundation
import PDFKit

let raw = FileHandle.standardInput.readData(ofLength: 700_001)
func finish(_ valid: Bool, _ pages: Int = 0) -> Never {
    let value: [String: Any] = valid ? ["valid": true, "page_count": pages] : ["valid": false]
    let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    exit(valid ? 0 : 2)
}
guard raw.count > 0, raw.count <= 700_000, raw.starts(with: Data("%PDF-".utf8)),
      let document = PDFDocument(data: raw), !document.isLocked, document.pageCount > 0
else { finish(false) }
for index in 0..<document.pageCount {
    guard let page = document.page(at: index) else { finish(false) }
    let bounds = page.bounds(for: .mediaBox)
    guard bounds.width.isFinite, bounds.height.isFinite,
          bounds.width > 0, bounds.height > 0 else { finish(false) }
}
finish(true, document.pageCount)
