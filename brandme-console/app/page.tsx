import { ConsolePageHeader } from '@/components/console-page-header'
import { consoleNavigation } from '@/lib/shell'
export default function ConsoleHome() {
  return (
    <>
      <ConsolePageHeader
        eyebrow="Operator workspace"
        title="A clear view of what needs you."
        description="Providers, permissions, and the moments that need a human decision."
      />
      <section className="console-notice" aria-labelledby="access-heading">
        <h2 id="access-heading">Operational access is not connected.</h2>
        <p>
          This shell does not establish a session, grant a role, or verify a
          provider. Protected records stay unavailable until the identity and
          domain services are connected.
        </p>
      </section>
      <section className="console-section" aria-labelledby="areas-heading">
        <h2 id="areas-heading">Your operational areas</h2>
        <p>
          Domain pages are added by their owning teams. Each must verify access
          before loading records or accepting an action.
        </p>
        <div className="console-grid">
          {consoleNavigation
            .filter((item) => item.href !== '/')
            .map(({ href, label }) => (
              <article key={href}>
                <span className="console-eyebrow">Integration pending</span>
                <h3>{label}</h3>
                <code>{href}</code>
                <p>No operational data loaded.</p>
              </article>
            ))}
        </div>
      </section>
    </>
  )
}
