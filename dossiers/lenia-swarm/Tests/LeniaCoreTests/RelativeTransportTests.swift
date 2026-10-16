import Foundation
import Metal
import XCTest
@testable import LeniaCore

final class RelativeTransportTests: XCTestCase {
    func testTransportFixtures() throws {
        let device = try XCTUnwrap(MTLCreateSystemDefaultDevice())
        let queue = try XCTUnwrap(device.makeCommandQueue())
        var records: [[String: Any]] = []
        for torus in [false, true] {
            let n = 32, channels = 2
            let source = FlowLeniaMetalFullPipeline.kernelSource(kernelCount: 1, parameterCount: 1, batchCount: 1, channelCount: channels, kernelBatchCount: 1, summaryPartialGroupCount: 1, sx: n, sy: n, dt: 0.2, dd: 5, sigma: 0.65, thetaA: 2, n: 2, useTorus: torus, alphaMode: "mass", flowClip: "none", parameterFieldMode: .none, reintegrateParams: false, parameterMixMode: .average)
            let lib = try device.makeLibrary(source: source, options: nil)
            let pipeline = try device.makeComputePipelineState(function: XCTUnwrap(lib.makeFunction(name: "flowMetalReintegrateAverage")))
            for kind in ["impulse", "uniform", "edge", "corner", "interior"] {
                var a = [Float](repeating: 0, count: n*n*channels)
                var f = [Float](repeating: 0, count: n*n*channels*2)
                for x in 0..<n { for y in 0..<n { for c in 0..<channels {
                    let i = (x*n+y)*channels+c
                    let occupied = kind == "uniform" || (kind == "impulse" && x == 16 && y == 16) || (kind == "edge" && x == 0 && y == 16) || (kind == "corner" && x == 0 && y == 0) || (kind == "interior" && x >= 12 && x < 20 && y >= 12 && y < 20)
                    if occupied { a[i] = kind == "uniform" ? 0.25 : Float((x*3+y*7+c*5)%11+1)/20 }
                    f[2*i] = kind == "impulse" ? 0 : (kind == "edge" || kind == "corner" ? -30 : 0.37)
                    f[2*i+1] = kind == "impulse" ? 0 : (kind == "corner" ? -30 : -0.61)
                } } }
                func buffer(_ values: [Float]) -> MTLBuffer { values.withUnsafeBytes { device.makeBuffer(bytes: $0.baseAddress!, length: $0.count, options: .storageModeShared)! } }
                let ab=buffer(a), fb=buffer(f), dummy=buffer([0]), output=buffer(a.map{_ in 0})
                let cb=try XCTUnwrap(queue.makeCommandBuffer()), e=try XCTUnwrap(cb.makeComputeCommandEncoder())
                e.setComputePipelineState(pipeline)
                for (i,b) in [ab,dummy,fb,output,dummy].enumerated(){e.setBuffer(b,offset:0,index:i)}
                let uniforms:[UInt32]=[0,0];uniforms.withUnsafeBytes{e.setBytes($0.baseAddress!,length:$0.count,index:5)}
                e.dispatchThreads(MTLSize(width:n,height:n,depth:1),threadsPerThreadgroup:MTLSize(width:8,height:8,depth:1));e.endEncoding();cb.commit();cb.waitUntilCompleted();XCTAssertNil(cb.error)
                let result=Array(UnsafeBufferPointer(start:output.contents().assumingMemoryBound(to:Float.self),count:a.count))
                var ref=[Double](repeating:0,count:a.count)
                let sigma=Double(Float(0.65)),dt=Double(Float(0.2)),ma=5-sigma
                for x in 0..<n { for y in 0..<n { for c in 0..<channels {
                    let i=(x*n+y)*channels+c;if a[i]==0 {continue}
                    var mx=Double(x)+0.5+min(ma,max(-ma,dt*Double(f[2*i])))
                    var my=Double(y)+0.5+min(ma,max(-ma,dt*Double(f[2*i+1])))
                    if !torus {mx=min(Double(n)-sigma,max(sigma,mx));my=min(Double(n)-sigma,max(sigma,my))}
                    for tx in 0..<n {for ty in 0..<n {
                        var dx=abs(Double(tx)+0.5-mx),dy=abs(Double(ty)+0.5-my)
                        if torus {dx=min(dx,abs(dx-Double(n)));dy=min(dy,abs(dy-Double(n)))}
                        let wx=min(1,min(2*sigma,max(0,0.5-dx+sigma))),wy=min(1,min(2*sigma,max(0,0.5-dy+sigma)))
                        ref[(tx*n+ty)*channels+c]+=Double(a[i])*wx*wy/(4*sigma*sigma)
                    }}
                } } }
                let total=a.reduce(0.0){$0+Double($1)}
                let l1=zip(result,ref).reduce(0.0){$0+abs(Double($1.0)-$1.1)}/total
                let drift=abs(result.reduce(0.0){$0+Double($1)}/total-1)
                XCTAssertLessThan(l1,2e-6,"\(kind) torus=\(torus)");XCTAssertLessThan(drift,2e-6);XCTAssertTrue(result.allSatisfy{$0>=0 && $0.isFinite})
                records.append(["fixture":kind,"torus":torus,"l1_vs_float64":l1,"relative_mass_error":drift])
            }
        }
        if let output=ProcessInfo.processInfo.environment["TRANSPORT_VALIDATION_OUTPUT"] {try JSONSerialization.data(withJSONObject:records,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:output))}
    }
}
