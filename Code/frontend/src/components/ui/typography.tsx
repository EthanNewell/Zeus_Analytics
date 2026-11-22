import type { HTMLAttributes } from "react"
import { cn } from "@/lib/utils"
const styles = {
  h1: "text-4xl font-medium tracking-tight", h2: "text-3xl font-medium tracking-tight",
  h3: "text-2xl font-medium", h4: "text-xl font-medium", p: "text-base leading-6",
  small: "text-sm leading-5", blockquote: "border-l-2 pl-4 italic",
  code: "rounded bg-muted px-1.5 py-0.5 font-mono text-sm",
}
export function Typography({ as: Tag = "p", className, ...props }:
  HTMLAttributes<HTMLElement> & { as?: keyof typeof styles }) {
  return <Tag className={cn(styles[Tag], className)} {...props} />
}
