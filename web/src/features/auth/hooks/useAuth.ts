"use client"
import { useRouter } from "next/navigation"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"

export function useLogin() {
  const router = useRouter()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { email: string; password: string }) => {
      const { data, error } = await api.POST("/api/v1/auth/login", { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      // Clear any cached data from the previous session so user A's queries
      // can't leak into user B's view.
      qc.clear()
      router.replace("/dashboard")
    },
  })
}

export function useRegister() {
  const router = useRouter()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { email: string; password: string }) => {
      const { data, error } = await api.POST("/api/v1/auth/register", { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.clear()
      // Defer navigation by one event loop tick so the browser can process Set-Cookie
      // before the middleware checks for the auth cookie on the /dashboard request.
      setTimeout(() => router.replace("/dashboard"), 0)
    },
  })
}

export function useLogout() {
  const router = useRouter()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.POST("/api/v1/auth/logout"),
    onSuccess: () => {
      // Clear persisted UI state + cached queries so the next user doesn't see stale data.
      localStorage.removeItem("yomochi.ui")
      qc.clear()
      router.replace("/login")
    },
    onError: () => {
      qc.clear()
      router.replace("/login")
    },
  })
}
