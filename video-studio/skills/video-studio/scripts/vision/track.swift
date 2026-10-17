// Where the speaker's face, hands and arms are, per frame, with Apple Vision (macOS only).
// Used by head_clean.py to tell the speaker's head from a picture hanging behind it.
// Compiled once by head_clean.py into the skill's state folder (needs Apple's free command line tools).
//
// Usage: track <video> <out.json>
//   -> [{"f":n,"face":[x,y,w,h],"hands":[{"WRI":[x,y],...}],"arms":[{"ls":[x,y],"le":[x,y],...}]}, ...]
//   pixels of the video, y down; "face" is [] when there is none (largest face wins)
import AVFoundation
import Foundation
import Vision

let args = CommandLine.arguments
if args.count < 3 {
    FileHandle.standardError.write("usage: track <video> <out.json>\n".data(using: .utf8)!)
    exit(2)
}
let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
guard let track = asset.tracks(withMediaType: .video).first else {
    FileHandle.standardError.write("no video track\n".data(using: .utf8)!)
    exit(1)
}
let size = track.naturalSize
let reader = try! AVAssetReader(asset: asset)
let out = AVAssetReaderTrackOutput(track: track, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
out.alwaysCopiesSampleData = false
reader.add(out)
reader.startReading()

func px(_ p: CGPoint) -> String {
    return "[\(Int(p.x * size.width)),\(Int((1 - p.y) * size.height))]"
}

let bodyKeys: [(VNHumanBodyPoseObservation.JointName, String)] = [
    (.leftShoulder, "ls"), (.leftElbow, "le"), (.leftWrist, "lw"),
    (.rightShoulder, "rs"), (.rightElbow, "re"), (.rightWrist, "rw"), (.neck, "nk"),
]
var rows: [String] = []
var n = 0
while let sb = out.copyNextSampleBuffer() {
    guard let pb = CMSampleBufferGetImageBuffer(sb) else { continue }
    let faceReq = VNDetectFaceRectanglesRequest()
    let handReq = VNDetectHumanHandPoseRequest()
    handReq.maximumHandCount = 2
    let bodyReq = VNDetectHumanBodyPoseRequest()
    try? VNImageRequestHandler(cvPixelBuffer: pb, options: [:]).perform([faceReq, handReq, bodyReq])

    var face = "[]"
    var best: VNFaceObservation? = nil
    for o in faceReq.results ?? [] where best == nil || o.boundingBox.width > best!.boundingBox.width { best = o }
    if let b = best?.boundingBox {
        let x = b.origin.x * size.width, w = b.width * size.width
        let h = b.height * size.height, y = (1 - b.origin.y - b.height) * size.height
        face = "[\(Int(x)),\(Int(y)),\(Int(w)),\(Int(h))]"
    }
    var hands: [String] = []
    for o in handReq.results ?? [] {
        var parts: [String] = []
        if let pts = try? o.recognizedPoints(.all) {
            for (k, p) in pts where p.confidence > 0.2 {
                parts.append("\"\(k.rawValue.rawValue.replacingOccurrences(of: "VNHLK", with: ""))\":" + px(p.location))
            }
        }
        hands.append("{" + parts.joined(separator: ",") + "}")
    }
    var arms: [String] = []
    for o in bodyReq.results ?? [] {
        var parts: [String] = []
        for (k, name) in bodyKeys {
            if let p = try? o.recognizedPoint(k), p.confidence > 0.2 { parts.append("\"\(name)\":" + px(p.location)) }
        }
        arms.append("{" + parts.joined(separator: ",") + "}")
    }
    let t = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sb))
    rows.append("{\"f\":\(n),\"t\":\(String(format: "%.4f", t)),\"face\":\(face),\"hands\":[" + hands.joined(separator: ",") + "],\"arms\":[" + arms.joined(separator: ",") + "]}")
    n += 1
}
if reader.status == .failed {
    FileHandle.standardError.write("could not read the video: \(reader.error?.localizedDescription ?? "?")\n".data(using: .utf8)!)
    exit(1)
}
try! ("[\n" + rows.joined(separator: ",\n") + "\n]\n").write(toFile: args[2], atomically: true, encoding: .utf8)
print("frames", n)
