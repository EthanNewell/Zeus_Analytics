// Render the real UI components at build time so Django can serve the form without JavaScript.
import { createServer } from "vite"
import { writeFile } from "node:fs/promises"
const server = await createServer({ server: { middlewareMode: true, ws: false, hmr: false }, appType: "custom" })
try {
  const { renderForm } = await server.ssrLoadModule("/src/auth-form.tsx")
  await writeFile("../templates/registration/_auth_card.html", "{# Generated from frontend/src/auth-form.tsx #}\n" + renderForm() + "\n")
} finally {
  await server.close()
}
