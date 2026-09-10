import { FiArrowUpRight } from "react-icons/fi"

export function DocsLink({ href, children = "Docs" }: { href: string; children?: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-0.5 text-link transition-colors duration-150 ease-out hover:text-link-hover focus-visible:otari-focus-ring motion-reduce:transition-none"
    >
      {children}
      <FiArrowUpRight aria-hidden="true" className="h-3 w-3" />
    </a>
  )
}
