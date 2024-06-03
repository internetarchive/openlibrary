export function initDarkMode(darkMode) {
  darkMode.addEventListener("click", function () {
    const body = document.querySelector("body");
    const icon = document.getElementById("darkModeIcon");
    const cookie = document.cookie;
    if (!cookie.includes("dm=True")) {
      document.cookie = "dm=True;";
      body.classList.add("dark-theme");
      icon.src = "./static/images/sunIcon.png";
    } else {
      document.cookie = "dm=; path=/";
      body.classList.remove("dark-theme");
      icon.src = "./static/images/moonIcon.png";
    }
  });
}
