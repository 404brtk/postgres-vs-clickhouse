(function () {
    if (window.__tracker_initialized__) return;
    window.__tracker_initialized__ = true;

    const currentScript =
        document.getElementById("tracker-script") || document.currentScript;
    let trackerEndpoint = currentScript
        ? currentScript.getAttribute("data-endpoint") || "/api/analytics/ingest"
        : "/api/analytics/ingest";

    window.setTrackerEndpoint = function (url) {
        trackerEndpoint = url;
    };

    function getRequestHeaders() {
        return { "Content-Type": "application/json" };
    }

    let entryTime = performance.now();

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
            const response = await fetch(trackerEndpoint, {
                method: "POST",
                headers: getRequestHeaders(),
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

    function buildEvent(eventType, properties = {}) {
        const event = {
            target_id: parseInt(properties.target_id, 10) || 0,
            category_id: parseInt(properties.category_id, 10) || 0,
            event_type: eventType,
            duration_sec: parseInt(properties.duration_sec, 10) || 0,
            is_liked: properties.is_liked ? 1 : 0,
            device: getDeviceType(),
            pathname: window.location.pathname,
            referrer: document.referrer,
            commission: parseFloat(properties.commission) || 0.0,
        };

        if (eventType === "click" && !properties.commission) {
            event.commission =
                Math.round((Math.random() * 2.45 + 0.05) * 100) / 100;
        } else if (eventType === "share" && !properties.commission) {
            event.commission =
                Math.round((Math.random() * 4.5 + 0.5) * 100) / 100;
        }

        const standardKeys = [
            "target_id",
            "category_id",
            "event_type",
            "duration_sec",
            "is_liked",
            "device",
            "pathname",
            "referrer",
            "commission",
        ];
        for (const [key, value] of Object.entries(properties)) {
            if (!standardKeys.includes(key)) {
                event[key] = value;
            }
        }

        return event;
    }

    function track(eventType, properties = {}) {
        const event = buildEvent(eventType, properties);
        window.dispatchEvent(
            new CustomEvent("tracker:track", {
                detail: { event },
            }),
        );
        send(event);
    }

    let exitSent = false;
    function sendExit() {
        if (exitSent) return;
        exitSent = true;
        const durationSec = Math.round((performance.now() - entryTime) / 1000);
        const event = buildEvent("exit", { duration_sec: durationSec });
        fetch(trackerEndpoint, {
            method: "POST",
            headers: getRequestHeaders(),
            body: JSON.stringify(event),
            keepalive: true,
        }).catch(() => {});
        window.dispatchEvent(
            new CustomEvent("tracker:track", {
                detail: { event },
            }),
        );
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
        const props = {};
        for (const attr of target.attributes) {
            if (attr.name.startsWith("data-")) {
                const key = attr.name.substring(5);
                if (key === "event") continue;

                if (key === "target") props["target_id"] = attr.value;
                else if (key === "category") props["category_id"] = attr.value;
                else if (key === "liked")
                    props["is_liked"] = attr.value === "true";
                else if (key === "duration") props["duration_sec"] = attr.value;
                else if (key === "commission") props["commission"] = attr.value;
                else props[key.replace(/-/g, "_")] = attr.value;
            }
        }

        track(eventType, props);
    });

    document.addEventListener("pagehide", sendExit);
    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "hidden") {
            sendExit();
        } else {
            exitSent = false;
            entryTime = performance.now();
        }
    });
})();
