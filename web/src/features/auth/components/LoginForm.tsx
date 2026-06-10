"use client"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useLogin } from "../hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import Link from "next/link"

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
})
type Fields = z.infer<typeof schema>

export function LoginForm() {
  const login = useLogin()
  const { register, handleSubmit, formState: { errors } } = useForm<Fields>({
    resolver: zodResolver(schema),
  })

  return (
    <form onSubmit={handleSubmit((data) => login.mutate(data))}
      className="w-full max-w-sm space-y-6">
      <h1 className="font-serif text-2xl text-[var(--text)]">Sign in</h1>

      <div className="space-y-2">
        <Label htmlFor="email" className="text-[var(--text-2)] text-xs uppercase tracking-widest">
          Email
        </Label>
        <Input id="email" type="email" {...register("email")}
          className="bg-transparent border-[var(--rule-strong)] text-[var(--text)]" />
        {errors.email && <p className="text-[var(--danger)] text-xs">{errors.email.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password" className="text-[var(--text-2)] text-xs uppercase tracking-widest">
          Password
        </Label>
        <Input id="password" type="password" {...register("password")}
          className="bg-transparent border-[var(--rule-strong)] text-[var(--text)]" />
        {errors.password && <p className="text-[var(--danger)] text-xs">{errors.password.message}</p>}
      </div>

      {login.isError && (
        <p className="text-[var(--danger)] text-sm">Invalid email or password.</p>
      )}

      <Button type="submit" disabled={login.isPending}
        className="w-full bg-[var(--accent)] text-[var(--fab-fg)]">
        {login.isPending ? "Signing in…" : "Sign in"}
      </Button>

      <p className="text-center text-sm text-[var(--text-3)]">
        No account?{" "}
        <Link href="/register" className="text-[var(--accent)] hover:underline">
          Register
        </Link>
      </p>
    </form>
  )
}
