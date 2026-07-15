(function () {
    if (window.__tracker_initialized__) return;
    window.__tracker_initialized__ = true;

    const currentScript =
        document.querySelector('[src*="/static/tracker.js"]') || document.currentScript;
    let trackerEndpoint = currentScript
        ? currentScript.getAttribute("data-endpoint") || "/api/analytics/ingest"
        : "/api/analytics/ingest";

    window.setTrackerEndpoint = function (url) {
        trackerEndpoint = url;
    };

    function getRequestHeaders() {
        return { "Content-Type": "application/json" };
    }

    let activeDuration = 0;
    let lastInteractionTime = Date.now();
    let currentPathname = window.location.pathname;

    function recordInteraction() {
        lastInteractionTime = Date.now();
    }

    window.addEventListener("mousemove", recordInteraction);
    window.addEventListener("keydown", recordInteraction);
    window.addEventListener("scroll", recordInteraction);
    window.addEventListener("click", recordInteraction);

    setInterval(function () {
        if (document.visibilityState !== "hidden" && (Date.now() - lastInteractionTime) < 30000) {
            activeDuration++;
        }
    }, 1000);

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
            event_type: eventType,
            device: getDeviceType(),
            pathname: properties.pathname || currentPathname,
            referrer: document.referrer,
            duration_sec: parseInt(properties.duration_sec, 10) || 0,
        };

        for (const [key, value] of Object.entries(properties)) {
            if (key !== "device" && key !== "pathname" && key !== "referrer" && key !== "duration_sec") {
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
    function sendExit(pathname = currentPathname) {
        if (exitSent) return;
        exitSent = true;
        const event = buildEvent("exit", {
            duration_sec: activeDuration,
            pathname: pathname
        });
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

    function handleTransition(newPathname) {
        sendExit(currentPathname);
        currentPathname = newPathname;
        activeDuration = 0;
        exitSent = false;
        lastInteractionTime = Date.now();
        track("pageview");
    }

    const originalPushState = window.history.pushState;
    if (originalPushState) {
        window.history.pushState = function (...args) {
            const newUrl = args[2];
            if (newUrl) {
                const parser = document.createElement("a");
                parser.href = newUrl;
                if (parser.pathname !== currentPathname) {
                    handleTransition(parser.pathname);
                }
            }
            return originalPushState.apply(this, args);
        };
    }

    const originalReplaceState = window.history.replaceState;
    if (originalReplaceState) {
        window.history.replaceState = function (...args) {
            const newUrl = args[2];
            if (newUrl) {
                const parser = document.createElement("a");
                parser.href = newUrl;
                if (parser.pathname !== currentPathname) {
                    handleTransition(parser.pathname);
                }
            }
            return originalReplaceState.apply(this, args);
        };
    }

    window.addEventListener("popstate", function () {
        handleTransition(window.location.pathname);
    });

    document.addEventListener("click", function (e) {
        const customTarget = e.target.closest("[data-event]");
        if (customTarget) {
            const eventType = customTarget.getAttribute("data-event");
            const props = {};
            for (const attr of customTarget.attributes) {
                if (attr.name.startsWith("data-")) {
                    const key = attr.name.substring(5);
                    if (key === "event") continue;
                    props[key.replace(/-/g, "_")] = attr.value;
                }
            }
            track(eventType, props);
            return;
        }

        const link = e.target.closest("a");
        if (link && link.href) {
            const isExternal = link.hostname && link.hostname !== window.location.hostname;
            const isProtocol = link.href.startsWith("http://") || link.href.startsWith("https://");
            if (isExternal && isProtocol) {
                track("outbound_click", {
                    target_url: link.href,
                    link_text: link.innerText.trim().substring(0, 100)
                });
            }
        }
    });

    document.addEventListener("pagehide", function () {
        sendExit(currentPathname);
    });
    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "hidden") {
            sendExit(currentPathname);
        } else {
            exitSent = false;
            activeDuration = 0;
            lastInteractionTime = Date.now();
        }
    });
})();
