"use client"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useRegister } from "../hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import Link from "next/link"

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  confirmPassword: z.string().min(8),
}).refine((d) => d.password === d.confirmPassword, {
  message: "Passwords do not match",
  path: ["confirmPassword"],
})
type Fields = z.infer<typeof schema>

export function RegisterForm() {
  const register_ = useRegister()
  const { register, handleSubmit, formState: { errors } } = useForm<Fields>({
    resolver: zodResolver(schema),
  })

  return (
    <form onSubmit={handleSubmit((data) => register_.mutate({ email: data.email, password: data.password }))}
      className="w-full max-w-sm space-y-6">
      <h1 className="font-serif text-2xl text-[var(--text)]">Create account</h1>

      <div className="space-y-2">
        <Label htmlFor="email" className="text-[var(--text-2)] text-xs uppercase tracking-widest">Email</Label>
        <Input id="email" type="email" {...register("email")}
          className="bg-transparent border-[var(--rule-strong)] text-[var(--text)]" />
        {errors.email && <p className="text-[var(--danger)] text-xs">{errors.email.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password" className="text-[var(--text-2)] text-xs uppercase tracking-widest">Password</Label>
        <Input id="password" type="password" {...register("password")}
          className="bg-transparent border-[var(--rule-strong)] text-[var(--text)]" />
        {errors.password && <p className="text-[var(--danger)] text-xs">{errors.password.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="confirmPassword" className="text-[var(--text-2)] text-xs uppercase tracking-widest">Confirm password</Label>
        <Input id="confirmPassword" type="password" {...register("confirmPassword")}
          className="bg-transparent border-[var(--rule-strong)] text-[var(--text)]" />
        {errors.confirmPassword && <p className="text-[var(--danger)] text-xs">{errors.confirmPassword.message}</p>}
      </div>

      {register_.isError && (
        <p className="text-[var(--danger)] text-sm">Registration failed. Try a different email.</p>
      )}

      <Button type="submit" disabled={register_.isPending}
        className="w-full bg-[var(--accent)] text-[var(--fab-fg)]">
        {register_.isPending ? "Creating account…" : "Create account"}
      </Button>

      <p className="text-center text-sm text-[var(--text-3)]">
        Already have an account?{" "}
        <Link href="/login" className="text-[var(--accent)] hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  )
}
