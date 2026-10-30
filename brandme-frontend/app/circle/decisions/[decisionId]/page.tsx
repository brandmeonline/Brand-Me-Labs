import { PageHeading } from '@/components/shell/page-heading'
import { DecisionView } from '@/features/social/circle'
export default async function Page({params}:{params:Promise<{decisionId:string}>}){const {decisionId}=await params;return <><PageHeading eyebrow="Circle / Decision" title="An honest opinion."/><DecisionView id={decisionId}/></>}
