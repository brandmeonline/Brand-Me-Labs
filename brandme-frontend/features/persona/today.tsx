'use client'
import Link from 'next/link'
import type {components} from '@brandme/contracts'
import {useResource} from '@/lib/client/use-resource'
import {ResourceState} from '@/components/ui/resource-state'
import {RecommendationList} from './recommendations'
import type {Recommendations} from './types'
export function TodayData(){
  const recommendations=useResource<Recommendations>('/recommendations')
  const wardrobe=useResource<{items:components['schemas']['WardrobeItem'][]}>('/wardrobe/items?collection=owned&limit=6')
  return <div className="bm-flow-stack">
    <section><h2 className="bm-section-title">Considered for you</h2><ResourceState {...recommendations} retry={recommendations.reload}/>{recommendations.data&&<RecommendationList data={recommendations.data}/>}</section>
    <section><h2 className="bm-section-title">Already in your wardrobe</h2><ResourceState {...wardrobe} retry={wardrobe.reload}/>{wardrobe.data?.items.length===0&&<p>Your wardrobe is ready for its first piece. <Link href="/add">Add something you own</Link>.</p>}
      <div className="bm-choice-grid">{wardrobe.data?.items.map(item=><article className="bm-flow-card" key={item.id}><h3><Link href={`/closet/items/${item.id}`}>{item.title}</Link></h3><p>{item.collection.replaceAll('_',' ')} · {item.claim_level.replaceAll('_',' ')}</p></article>)}</div>
    </section>
  </div>
}
