// KateApp.swift
// Entry point. Registers for push notifications and routes a tapped
// Kate notification to the recommendation screen.

import SwiftUI
import UIKit
import UserNotifications

@main
struct KateApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var router = Router.shared
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            HomeView()
                .environmentObject(router)
                // SECURITY: hide balances in the app switcher snapshot.
                .overlay { if scenePhase != .active { PrivacyShield() } }
        }
    }
}

/// Holds which recommendation should be shown after a notification tap.
@MainActor
final class Router: ObservableObject {
    static let shared = Router()
    @Published var pendingRecommendationId: String?
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        NotificationManager.shared.configure()
        return true
    }

    // Apple gives us a device token -> send it to KBC (only when logged in).
    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { try? await APIClient.shared.registerDevice(token: hex) }
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("Push registration failed: \(error.localizedDescription)")
    }
}

/// Plain cover shown while the app is in the background.
struct PrivacyShield: View {
    var body: some View {
        ZStack {
            Color(red: 0.05, green: 0.05, blue: 0.06).ignoresSafeArea()
            Image(systemName: "lock.fill").font(.largeTitle).foregroundStyle(.white)
        }
    }
}
