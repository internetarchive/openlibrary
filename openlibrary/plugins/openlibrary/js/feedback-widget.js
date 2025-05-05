export function initSubjectFeedback() {
    const widget = document.getElementById("feedback-widget");
    const message = document.getElementById("feedback-message");
  
    function sendFeedback(score) {
      const payload = {
        key: window.location.pathname,
        score,
        patron_name: window.OL_USER?.key || "anonymous",
        country: "unknown"  // Ideally get this from web.ctx or user profile
      };
  
      fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(res => {
        if (res.ok) {
          widget.style.display = "none";
          message.style.display = "block";
          setTimeout(() => message.style.display = "none", 3000);
        }
      });
    }
  
    window.submitFeedback = sendFeedback;
    window.dismissWidget = () => { widget.style.display = "none"; };
  }
  