'use client'

import { useRef, useState } from 'react'
import { Button, ActionLink } from './button'
import { Input, Select, Switch } from './field'
import { Slider } from './slider'
import { Tabs } from './tabs'
import { Dialog, Drawer } from './dialog'
import { EmptyState, ErrorState, Skeleton, StatusChip, Toast } from './feedback'
import { Price } from './price'
import { EvidenceLabel } from './evidence-label'

export function ComponentGallery() {
  const [expression, setExpression] = useState<number | null>(null)
  const [tab, setTab] = useState('declared')
  const [enabled, setEnabled] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const noticeTrigger = useRef<HTMLButtonElement>(null)
  return (
    <div className="bm-gallery">
      <p className="bm-identity-note">
        Development fixture only. No profile, order, points or fit claim is
        saved or verified here.
      </p>
      <section className="bm-gallery-section" aria-labelledby="gallery-actions">
        <p className="bm-eyebrow">01 / Actions</p>
        <h2 id="gallery-actions" className="bm-section-title">
          Clear intent, visible state.
        </h2>
        <div className="bm-ui-actions">
          <Button
            ref={noticeTrigger}
            onClick={() =>
              setNotice(
                'Example action received. Nothing was saved to an account.',
              )
            }
          >
            Show example notice
          </Button>
          <ActionLink href="/settings">Display settings</ActionLink>
          <Button pending pendingLabel="Example: saving…">
            Save example
          </Button>
          <Button disabled variant="secondary">
            Unavailable action
          </Button>
        </div>
        <Toast
          message={notice}
          onDismiss={() => {
            setNotice(null)
            noticeTrigger.current?.focus()
          }}
        />
      </section>

      <section className="bm-gallery-section" aria-labelledby="gallery-fields">
        <p className="bm-eyebrow">02 / Choices</p>
        <h2 id="gallery-fields" className="bm-section-title">
          A choice you can change.
        </h2>
        <div className="bm-ui-grid">
          <Input
            label="Example intention"
            description="A local text-field demonstration, not a saved intention."
            placeholder="A quieter kind of statement"
          />
          <Select label="Example occasion" defaultValue="everyday">
            <option value="everyday">Everyday</option>
            <option value="work">Work</option>
            <option value="going-out">Going out</option>
          </Select>
          <Input
            label="Example error"
            defaultValue="101"
            error="Example validation: enter a value no greater than 100."
          />
          <Input
            label="Read-only example"
            value="No account connected"
            readOnly
          />
        </div>
        <Switch
          label="Example switch"
          description="A local control demonstration. It grants no permission."
          checked={enabled}
          onCheckedChange={setEnabled}
        />
        <Slider
          label="Expression"
          leftLabel="Understated"
          rightLabel="Expressive"
          value={expression}
          onValueChange={setExpression}
        />
        <Slider
          label="Locked example"
          leftLabel="Tailored"
          rightLabel="Relaxed"
          value={60}
          disabled
          onValueChange={() => {}}
        />
      </section>

      <section className="bm-gallery-section" aria-labelledby="gallery-panels">
        <p className="bm-eyebrow">03 / Context</p>
        <h2 id="gallery-panels" className="bm-section-title">
          Show the difference.
        </h2>
        <Tabs
          label="Preference record examples"
          value={tab}
          onValueChange={setTab}
          items={[
            {
              id: 'declared',
              label: 'Declared',
              content: (
                <p>An explicit choice. This gallery has not saved a profile.</p>
              ),
            },
            {
              id: 'inferred',
              label: 'Inferred',
              content: (
                <p>No inference exists. Unknown is not a neutral score.</p>
              ),
            },
            {
              id: 'effective',
              label: 'Effective',
              content: (
                <p>
                  The value used by the recommender belongs to its actual API
                  response.
                </p>
              ),
            },
            {
              id: 'unavailable',
              label: 'Unavailable',
              disabled: true,
              content: <p>Not connected.</p>,
            },
          ]}
        />
        <div className="bm-ui-actions">
          <Dialog
            title="Example confirmation"
            description="This demonstrates a focus-managed dialog. It does not approve a purchase."
            trigger={<Button variant="secondary">Open example dialog</Button>}
          >
            <Input
              label="Example note"
              placeholder="Keyboard focus stays in this dialog"
            />
          </Dialog>
          <Drawer
            title="Example drawer"
            description="The existing shell drawer, with equivalent keyboard height controls."
            trigger={<Button variant="secondary">Open example drawer</Button>}
          >
            <p>
              No account data is loaded here. Escape returns focus to the
              trigger.
            </p>
          </Drawer>
        </div>
      </section>

      <section
        className="bm-gallery-section"
        aria-labelledby="gallery-feedback"
      >
        <p className="bm-eyebrow">04 / Feedback</p>
        <h2 id="gallery-feedback" className="bm-section-title">
          Honest, ordinary states.
        </h2>
        <div className="bm-ui-actions">
          <StatusChip>Not connected</StatusChip>
          <StatusChip tone="warning">Example: pending</StatusChip>
          <StatusChip tone="success">Example: completed</StatusChip>
          <StatusChip tone="error">Example: failed</StatusChip>
        </div>
        <EmptyState
          title="Nothing here yet."
          description="A demonstration of an empty state, not a query of your wardrobe."
        />
        <ErrorState
          title="Example connection error"
          description="No data was changed. In a connected flow, offer an idempotent retry."
          action={<ActionLink href="/settings">Return to settings</ActionLink>}
        />
        <Skeleton label="Example loading placeholder; no request is running" />
      </section>

      <section
        className="bm-gallery-section"
        aria-labelledby="gallery-evidence"
      >
        <p className="bm-eyebrow">05 / Evidence</p>
        <h2 id="gallery-evidence" className="bm-section-title">
          Specific beats implied.
        </h2>
        <p>Illustrative prices only; no live offer or checkout is available.</p>
        <div className="bm-ui-actions">
          <Price money={{ amount_minor: '9612', currency: 'USD' }} />
          <Price money={{ amount_minor: '1234', currency: 'JPY' }} />
          <Price money={{ amount_minor: '1234', currency: 'KWD' }} />
          <Price money={null} />
        </div>
        <div className="bm-ui-grid">
          <EvidenceLabel kind="photo_display" />
          <EvidenceLabel kind="approximate_3d" />
          <EvidenceLabel kind="product_3d" />
          <EvidenceLabel kind="live_overlay" />
          <EvidenceLabel kind="generative_preview" />
          <p className="bm-evidence-label">
            Fit estimates are unavailable in this gallery. They require a
            validated method and explicit limits.
          </p>
        </div>
        <ActionLink href="/today">Return to Today</ActionLink>
      </section>
    </div>
  )
}
