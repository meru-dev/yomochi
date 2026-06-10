import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import { makeServerClient } from "@/lib/api/client"
import { UserProvider } from "@/lib/context/UserContext"
import { AppShell } from "@/components/shell/AppShell"

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies()
  const cookieHeader = cookieStore.toString()
  const serverApi = makeServerClient(cookieHeader)

  const { data, error } = await serverApi.GET("/api/v1/users/me")
  if (error || !data) redirect("/login")

  return (
    <UserProvider user={{ id: data.id, email: data.email }}>
      <AppShell>{children}</AppShell>
    </UserProvider>
  )
}
