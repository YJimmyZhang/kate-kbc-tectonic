// Views.swift
// HomeView: imaginary KBC home screen with the "Kate, just for you" card.
// RecommendationView: the full suggestion, opened after Face ID.

import LocalAuthentication
import SwiftUI

private let kbcBlue = Color(red: 0.24, green: 0.71, blue: 0.92)
private let card = Color(red: 0.11, green: 0.11, blue: 0.12)

// MARK: - Home
struct HomeView: View {
    @EnvironmentObject var router: Router
    @State private var openId: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("For you").font(.title2)

                    // Kate card: tapping opens the same flow as a notification.
                    Button { openId = "demo-lotte-0000000000000000" } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            Label("Kate, just for you", systemImage: "sparkle")
                                .font(.subheadline.bold()).foregroundStyle(kbcBlue)
                            Text("You have a new suggestion").font(.headline)
                            Text("See Kate's suggestion ›").font(.subheadline).foregroundStyle(kbcBlue)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(card, in: RoundedRectangle(cornerRadius: 16))
                        .overlay(RoundedRectangle(cornerRadius: 16).stroke(kbcBlue.opacity(0.6)))
                    }
                    .buttonStyle(.plain)

                    // Demo controls for the jury.
                    Button("Allow notifications") { Task { _ = await NotificationManager.shared.requestPermission() } }
                    Button("Send demo notification (lock the phone within 5 s)") {
                        NotificationManager.shared.sendDemoNotification()
                    }
                }
                .padding()
            }
            .navigationTitle("KBC")
            .navigationDestination(item: $openId) { RecommendationView(recommendationId: $0) }
        }
        .preferredColorScheme(.dark)
        // A notification tap sets pendingRecommendationId -> open it.
        .onChange(of: router.pendingRecommendationId) { _, id in
            if let id { openId = id; router.pendingRecommendationId = nil }
        }
    }
}

// MARK: - Recommendation
struct RecommendationView: View {
    let recommendationId: String
    @State private var rec: Recommendation?
    @State private var error: String?

    var body: some View {
        ScrollView {
            if let rec { content(rec) }
            else if let error { Text(error).foregroundStyle(.secondary).padding() }
            else { ProgressView().padding(.top, 80) }
        }
        .navigationTitle("For you")
        .task { await load() }
    }

    // SECURITY: financial advice is only shown after Face ID / passcode,
    // even if someone else taps the notification on an unlocked phone.
    private func load() async {
        let ctx = LAContext()
        do {
            guard try await ctx.evaluatePolicy(.deviceOwnerAuthentication,
                                               localizedReason: "Open Kate's suggestion") else { return }
            rec = try await APIClient.shared.recommendation(id: recommendationId)
        } catch APIError.notFound {
            error = "This suggestion is no longer available."
        } catch APIError.notLoggedIn {
            error = "Please log in first."
        } catch {
            self.error = "Could not open this suggestion."
        }
    }

    @ViewBuilder private func content(_ r: Recommendation) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("\(r.pathway.number)  \(r.pathway.name)")
                .font(.caption.bold()).padding(.horizontal, 10).padding(.vertical, 4)
                .background(kbcBlue.opacity(0.25), in: Capsule())

            Text(r.title).font(.title2.bold())
            Text(r.body).foregroundStyle(.secondary)

            // Product with risk scale 1-7; the customer's limit is highlighted.
            VStack(alignment: .leading, spacing: 8) {
                Text(r.pathway.product).font(.subheadline)
                if let risk = r.pathway.risk {
                    HStack(spacing: 4) {
                        ForEach(1...7, id: \.self) { n in
                            Text("\(n)").font(.caption.bold()).frame(maxWidth: .infinity, minHeight: 26)
                                .background(n == risk ? kbcBlue : n <= r.riskLimit ? kbcBlue.opacity(0.25) : Color.gray.opacity(0.2),
                                            in: RoundedRectangle(cornerRadius: 6))
                        }
                    }
                    Text("Indicative risk \(risk) of 7. Your limit: up to \(r.riskLimit).")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text("Keep in mind: \(r.pathway.keepInMind)").font(.caption).foregroundStyle(.secondary)
            }
            .padding().background(card, in: RoundedRectangle(cornerRadius: 16))

            Button(r.cta) { /* opens the product flow in the real app */ }
                .frame(maxWidth: .infinity, minHeight: 50)
                .background(kbcBlue, in: Capsule()).foregroundStyle(.white).bold()

            Text("Why Kate suggests this").font(.headline).padding(.top, 8)
            ForEach(r.reasons, id: \.self) { Label($0, systemImage: "circle.fill").font(.subheadline) }

            Text("Kate only uses data you already share with KBC, with your consent. The value of an investment can go down as well as up.")
                .font(.caption).foregroundStyle(.secondary).padding(.top, 8)
        }
        .padding()
    }
}
