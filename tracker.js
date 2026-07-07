(function () {
    if (window.__tracker_initialized__) return;
    window.__tracker_initialized__ = true;

    const currentScript =
        document.getElementById("tracker-script") || document.currentScript;
    const siteId = currentScript
        ? currentScript.getAttribute("data-site-id")
        : "default";
    const apiEndpoint = currentScript
        ? currentScript.getAttribute("data-endpoint") || ""
        : "";

    function getDeviceType() {
        const ua = navigator.userAgent.toLowerCase();
        if (/(tablet|ipad|playbook|silk)|(android(?!.*mobi))/i.test(ua)) {
            return "tablet";
        }
        if (
            /mobile|iphone|ipod|android|blackberry|opera mini|iemobile|wpdesktop/i.test(
                ua,
            )
        ) {
            return "mobile";
        }
        return "desktop";
    }

    async function send(event) {
        try {
            const response = await fetch(`${apiEndpoint}/api/events`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(event),
            });
            const data = await response.json();
            if (response.ok) {
                window.dispatchEvent(
                    new CustomEvent("tracker:ingested", {
                        detail: { event, data },
                    }),
                );
            }
        } catch (err) {
            console.error("Tracker ingestion failed:", err);
        }
    }

    function track(eventType, properties = {}) {
        const scriptTag =
            document.getElementById("tracker-script") || document.currentScript;
        const userId = scriptTag
            ? scriptTag.getAttribute("data-user-id")
            : null;

        const event = {
            user_id: userId ? parseInt(userId, 10) : null,
            target_id: parseInt(properties.target_id, 10) || 0,
            category_id: parseInt(properties.category_id, 10) || 0,
            event_type: eventType,
            duration_sec: parseInt(properties.duration_sec, 10) || 0,
            is_liked: properties.is_liked ? 1 : 0,
            device: getDeviceType(),
            commission: parseFloat(properties.commission) || 0.0,
        };

        if (eventType === "click" && !properties.commission) {
            event.commission =
                Math.round((Math.random() * 2.45 + 0.05) * 100) / 100;
        } else if (eventType === "share" && !properties.commission) {
            event.commission =
                Math.round((Math.random() * 4.5 + 0.5) * 100) / 100;
        }

        window.dispatchEvent(
            new CustomEvent("tracker:track", {
                detail: { event },
            }),
        );

        send(event);
    }

    track("pageview", {
        target_id: 0,
        category_id: 0,
        duration_sec: 0,
    });

    document.addEventListener("click", function (e) {
        const target = e.target.closest("[data-event]");
        if (!target) return;

        const eventType = target.getAttribute("data-event");
        const targetId = target.getAttribute("data-target") || 0;
        const categoryId = target.getAttribute("data-category") || 0;
        const isLiked = target.getAttribute("data-liked") === "true";
        const duration = target.getAttribute("data-duration") || 0;
        const commission = target.getAttribute("data-commission") || 0.0;

        track(eventType, {
            target_id: targetId,
            category_id: categoryId,
            is_liked: isLiked,
            duration_sec: duration,
            commission: commission,
        });
    });
})();
