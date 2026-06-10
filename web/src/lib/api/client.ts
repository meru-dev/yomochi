// Response validation policy: TypeScript types from `schema.d.ts` only.
// Backend (same monorepo) is trusted; CI gates contract drift via `make schema-check`.
// Form/input validation lives inline in feature folders with `zod`.
import createClient from "openapi-fetch"
import type { paths } from "./schema"

// Server-side client — used in Server Components; bypasses Next.js proxy, hits backend directly
export function makeServerClient(cookieHeader: string) {
  return createClient<paths>({
    baseUrl: process.env.API_URL ?? "http://localhost:8000",
    headers: { Cookie: cookieHeader },
  })
}

// Browser client — empty baseUrl makes requests relative to origin so they go through
// the Next.js /api/** rewrite proxy. SameSite=Lax cookie is same-origin; no CORS needed.
export const api = createClient<paths>({
  baseUrl: "",
  credentials: "include",
})

api.use({
  async onResponse({ response }) {
    if (
      response.status === 401 &&
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login")
    ) {
      window.location.replace("/login")
    }
    return response
  },
})
