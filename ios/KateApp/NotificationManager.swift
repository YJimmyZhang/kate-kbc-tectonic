// NotificationManager.swift
// Asks permission, receives Kate notifications and handles taps.
// Includes a LOCAL notification so the demo works without APNs certificates.

import Foundation
import UIKit
import UserNotifications

final class NotificationManager: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationManager()
    private let center = UNUserNotificationCenter.current()

    func configure() {
        center.delegate = self

        // SECURITY: `.hiddenPreviewsShowTitle` means that if the user hides
        // previews on the lock screen, iOS shows only "Kate", never the body.
        let category = UNNotificationCategory(
            identifier: "KATE_SUGGESTION",
            actions: [],                                  // no one-tap actions from the lock screen
            intentIdentifiers: [],
            hiddenPreviewsBodyPlaceholder: "New message",
            options: [.hiddenPreviewsShowTitle]
        )
        center.setNotificationCategories([category])
    }

    /// Ask the customer once, after explaining why (never on first launch).
    func requestPermission() async -> Bool {
        let granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        if granted {
            await MainActor.run { UIApplication.shared.registerForRemoteNotifications() }
        }
        return granted
    }

    // MARK: Demo: local notification with the SAME generic payload as the server.
    func sendDemoNotification(recommendationId: String = "demo-lotte-0000000000000000") {
        let content = UNMutableNotificationContent()
        content.title = "Kate"
        content.body = "You have a new suggestion. Open the app to view it."
        content.sound = .default
        content.categoryIdentifier = "KATE_SUGGESTION"
        content.threadIdentifier = "kate"
        content.userInfo = ["rid": recommendationId]

        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 5, repeats: false)
        center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: trigger))
    }

    // MARK: UNUserNotificationCenterDelegate

    // App is open: still show the banner.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }

    // User tapped the notification.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse) async {
        let info = response.notification.request.content.userInfo

        // SECURITY: treat the payload as untrusted input.
        // Only accept an id that matches the expected format. No URLs,
        // no web links, nothing that could be used for phishing redirects.
        guard let rid = info["rid"] as? String,
              rid.range(of: #"^[A-Za-z0-9_-]{22,64}$"#, options: .regularExpression) != nil
        else { return }

        await MainActor.run { Router.shared.pendingRecommendationId = rid }
    }
}
