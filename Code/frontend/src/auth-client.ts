import "./theme.css"
const password = document.querySelector<HTMLInputElement>("#id_password")
const toggle = document.querySelector<HTMLButtonElement>("#toggle-password")
if (password && toggle) {
  toggle.hidden = false
  toggle.addEventListener("click", () => {
    const visible = password.type === "password"
    password.type = visible ? "text" : "password"
    toggle.setAttribute("aria-pressed", String(visible))
    toggle.setAttribute("aria-label", visible ? "Скрыть пароль" : "Показать пароль")
  })
}
