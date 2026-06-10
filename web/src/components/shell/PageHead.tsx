interface PageHeadProps {
  crumb: string
  title: string
  subtitle?: string
  actions?: React.ReactNode
}

export function PageHead({ crumb, title, subtitle, actions }: PageHeadProps) {
  return (
    <div className="flex items-start justify-between mb-8">
      <div>
        <p className="font-mono text-[11px] text-[var(--text-3)] uppercase tracking-[0.04em] mb-1">
          {crumb}
        </p>
        <h1 className="font-serif text-[clamp(26px,3vw,36px)] text-[var(--text)] leading-[1.15] tracking-[-0.005em]">
          {title}
        </h1>
        {subtitle && (
          <p className="text-sm text-[var(--text-2)] mt-1">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  )
}
