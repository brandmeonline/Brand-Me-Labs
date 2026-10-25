import { PageHeading } from '@/components/shell/page-heading'
import { Connections } from '@/features/privacy/connections'
export const dynamic='force-dynamic'
export default function Page(){const allowDev=process.env.NODE_ENV!=='production'&&['demo','development'].includes(process.env.BRANDME_MODE??'');return <><PageHeading eyebrow="Me / Connections" title="Connected, with your permission." description="Review your account and the services allowed to act for you."/><Connections allowDev={allowDev}/></>}
