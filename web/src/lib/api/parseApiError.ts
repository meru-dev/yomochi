export interface FieldError {
  field: string
  message: string
}

export interface ApiError {
  fieldErrors: FieldError[]
  generalError: string | null
}

const CODE_TO_FIELD: Record<string, string> = {
  "transaction.invalid_amount": "amount",
  "transaction.invalid_currency": "currency",
  "transaction.invalid_amount_precision": "amount",
  "user.invalid_email": "email",
  "user.weak_password": "password",
}

export function parseApiError(err: unknown): ApiError {
  if (!err || typeof err !== "object") {
    return { fieldErrors: [], generalError: "Something went wrong" }
  }

  if ("error" in err && err.error !== null && typeof err.error === "object") {
    const { code, message } = err.error as { code?: string; message?: string }
    const field = code ? CODE_TO_FIELD[code] : undefined
    if (field) {
      return { fieldErrors: [{ field, message: message ?? "Invalid value" }], generalError: null }
    }
    return { fieldErrors: [], generalError: message ?? "Something went wrong" }
  }

  if ("detail" in err && Array.isArray((err as { detail: unknown }).detail)) {
    const detail = (err as { detail: Array<{ loc?: unknown[]; msg?: string }> }).detail
    const fieldErrors = detail.map((d) => ({
      field: String(d.loc?.at(-1) ?? "unknown"),
      message: d.msg ?? "Invalid value",
    }))
    return { fieldErrors, generalError: null }
  }

  return { fieldErrors: [], generalError: "Something went wrong" }
}
