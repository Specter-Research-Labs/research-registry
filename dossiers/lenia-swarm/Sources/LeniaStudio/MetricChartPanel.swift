import SwiftUI
import Charts

struct MetricChartPanel: View {
    let metricHistory: MetricHistory

    var body: some View {
        HStack(spacing: 16) {
            MetricLineChart(title: "Mass", data: metricHistory.mass, color: .orange)
            MetricLineChart(title: "Occupancy", data: metricHistory.occupancy, color: .cyan)
            MetricLineChart(title: "Velocity", data: metricHistory.velocity, color: .green)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .frame(height: 120)
        .background(.bar)
    }
}

struct MetricLineChart: View {
    let title: String
    let data: [Float]
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Chart {
                ForEach(Array(data.enumerated()), id: \.offset) { index, value in
                    LineMark(
                        x: .value("Step", index),
                        y: .value(title, Double(value))
                    )
                    .foregroundStyle(color)
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis {
                AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) {
                    AxisValueLabel()
                        .font(.system(size: 8))
                }
            }
        }
    }
}
