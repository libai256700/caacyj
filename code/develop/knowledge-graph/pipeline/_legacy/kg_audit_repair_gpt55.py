#!/usr/bin/env python3
"""Comprehensive Neo4j knowledge graph audit and repair.
- Merge duplicate nodes by name+label, preserving relationships/properties.
- Link legacy CAAC question-bank entities to CAAC理论考试.
- Link exam hierarchy to avoid orphan exam nodes.
"""
from pathlib import Path
from neo4j import GraphDatabase
from collections import defaultdict
import json, re, datetime

BASE_DIR = Path(__file__).parent.parent
URI='bolt://localhost:7687'
AUTH=('neo4j','yj123456')
OLD_DOCS=['飞行原理与飞行性能','概述','无人机教员题库']
EXAM_THEORY='CAAC理论考试'
EXAM_LICENSE='CAAC无人机执照考试'
EXAM_PRACTICE='CAAC实操考试'

def reltype(t):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', t):
        raise ValueError(f'Unsafe relationship type: {t}')
    return f'`{t}`'

def stats(session):
    data={}
    data['nodes']=session.run('MATCH (n) RETURN count(n) AS c').single()['c']
    data['relationships']=session.run('MATCH ()-[r]->() RETURN count(r) AS c').single()['c']
    data['labels']={r['label']:r['c'] for r in session.run('MATCH (n) UNWIND labels(n) AS label RETURN label,count(*) AS c ORDER BY c DESC')}
    data['relTypes']={r['type']:r['c'] for r in session.run('MATCH ()-[r]->() RETURN type(r) AS type,count(*) AS c ORDER BY c DESC')}
    data['duplicateGroups']=[dict(r) for r in session.run('MATCH (n) WHERE n.name IS NOT NULL WITH n.name AS name, labels(n) AS labels, count(n) AS c WHERE c>1 RETURN name, labels, c ORDER BY c DESC, name')]
    data['emptyEntityDescriptions']=session.run('MATCH (n:Entity) WHERE n.description IS NULL OR trim(toString(n.description))="" RETURN count(n) AS c').single()['c']
    data['orphanNodes']=[dict(r) for r in session.run('MATCH (n) WHERE NOT (n)--() RETURN labels(n) AS labels,n.name AS name,n.entityType AS entityType LIMIT 50')]
    data['knowledgePoints']=session.run('MATCH (n:Entity {entityType:"KnowledgePoint"}) RETURN count(n) AS c').single()['c']
    data['examTheoryLinks']=session.run('MATCH (:Entity {name:$name})-[:CONTAINS]->(n) RETURN count(n) AS c', name=EXAM_THEORY).single()['c']
    data['oldDocs']=[]
    for doc in OLD_DOCS:
        row=session.run('''MATCH (e:Entity)
            WHERE e.source_doc = $doc OR e.source_doc = $doc + '.txt' OR e.source_doc = $doc + '.docx' OR e.source = $doc
            WITH collect(DISTINCT e) AS ents
            RETURN size(ents) AS total,
                   size([x IN ents WHERE (:Entity {name:$exam})-[:CONTAINS]->(x)]) AS linked''', doc=doc, exam=EXAM_THEORY).single()
        data['oldDocs'].append({'doc':doc,'total':row['total'],'linked':row['linked'],'unlinked':row['total']-row['linked']})
    return data

def merge_properties(s_props, d_props):
    out={}
    aliases=set()
    for k,v in d_props.items():
        if k == 'name':
            continue
        sv=s_props.get(k)
        if sv in (None, '') and v not in (None, ''):
            out[k]=v
        elif sv is not None and v is not None and sv != v and k in ('description','source_doc','source','doc_url'):
            aliases.add(str(v))
    if aliases:
        old=s_props.get('merged_values')
        vals=[]
        if old:
            if isinstance(old, list): vals.extend(map(str, old))
            else: vals.append(str(old))
        vals.extend(sorted(aliases))
        out['merged_values']=sorted(set(vals))
    return out

def merge_group(session, name, label='Entity'):
    nodes=[dict(r) for r in session.run(f'''MATCH (n:{label} {{name:$name}})
        OPTIONAL MATCH (n)-[r]-()
        RETURN elementId(n) AS eid, properties(n) AS props, count(r) AS degree
        ORDER BY degree DESC, eid''', name=name)]
    if len(nodes) <= 1:
        return {'name':name,'merged':0,'createdRels':0,'deletedNodes':0,'skippedSelfLoops':0}
    survivor=nodes[0]
    s_eid=survivor['eid']
    s_props=survivor['props'] or {}
    created=0; deleted=0; skipped=0
    for dup in nodes[1:]:
        d_eid=dup['eid']
        # copy useful properties before deleting duplicate
        updates=merge_properties(s_props, dup.get('props') or {})
        if updates:
            session.run('MATCH (s) WHERE elementId(s)=$sid SET s += $props', sid=s_eid, props=updates)
            s_props.update(updates)
        # outgoing relationships
        outs=[dict(r) for r in session.run('''MATCH (d)-[r]->(m)
            WHERE elementId(d)=$did
            RETURN type(r) AS type, properties(r) AS props, elementId(m) AS mid''', did=d_eid)]
        for r in outs:
            if r['mid']==s_eid:
                skipped += 1; continue
            q=f'''MATCH (s),(m) WHERE elementId(s)=$sid AND elementId(m)=$mid
                  MERGE (s)-[nr:{reltype(r['type'])}]->(m)
                  SET nr += $props
                  RETURN count(nr) AS c'''
            session.run(q, sid=s_eid, mid=r['mid'], props=r['props'] or {})
            created += 1
        # incoming relationships
        ins=[dict(r) for r in session.run('''MATCH (m)-[r]->(d)
            WHERE elementId(d)=$did
            RETURN type(r) AS type, properties(r) AS props, elementId(m) AS mid''', did=d_eid)]
        for r in ins:
            if r['mid']==s_eid:
                skipped += 1; continue
            q=f'''MATCH (s),(m) WHERE elementId(s)=$sid AND elementId(m)=$mid
                  MERGE (m)-[nr:{reltype(r['type'])}]->(s)
                  SET nr += $props
                  RETURN count(nr) AS c'''
            session.run(q, sid=s_eid, mid=r['mid'], props=r['props'] or {})
            created += 1
        session.run('MATCH (d) WHERE elementId(d)=$did DETACH DELETE d', did=d_eid)
        deleted += 1
    return {'name':name,'merged':len(nodes)-1,'createdRels':created,'deletedNodes':deleted,'skippedSelfLoops':skipped}

def ensure_exam_nodes(session):
    exams=[
        (EXAM_THEORY,'中国民用航空局组织的无人机驾驶员理论考试，涵盖飞行原理、气象、法规等科目'),
        (EXAM_LICENSE,'CAAC无人机驾驶员执照资格认证考试，含理论和实操'),
        (EXAM_PRACTICE,'CAAC无人机驾驶员实际操作考试，含悬停、八字飞行、电子桩等'),
    ]
    for name,desc in exams:
        session.run('''MERGE (e:Entity {name:$name})
            SET e.description=$desc, e.entityType='Exam', e.category='考试' ''', name=name, desc=desc)
    session.run('''MATCH (license:Entity {name:$license}),(theory:Entity {name:$theory})
        MERGE (license)-[:CONTAINS]->(theory)''', license=EXAM_LICENSE, theory=EXAM_THEORY)
    session.run('''MATCH (license:Entity {name:$license}),(practice:Entity {name:$practice})
        MERGE (license)-[:CONTAINS]->(practice)''', license=EXAM_LICENSE, practice=EXAM_PRACTICE)

def link_old_question_banks(session):
    total=0; by_doc=[]
    for doc in OLD_DOCS:
        row=session.run('''MATCH (exam:Entity {name:$exam})
            MATCH (e:Entity)
            WHERE e.source_doc = $doc OR e.source_doc = $doc + '.txt' OR e.source_doc = $doc + '.docx' OR e.source = $doc
            WITH exam, collect(DISTINCT e) AS ents
            FOREACH (x IN ents | MERGE (exam)-[:CONTAINS]->(x))
            RETURN size(ents) AS linked''', exam=EXAM_THEORY, doc=doc).single()
        c=row['linked']; total += c; by_doc.append({'doc':doc,'linked':c})
    return {'totalMatched':total,'byDoc':by_doc}

def main():
    driver=GraphDatabase.driver(URI, auth=AUTH)
    report={'startedAt':datetime.datetime.now().isoformat()}
    with driver.session(database='neo4j') as session:
        before=stats(session); report['before']=before
        print('BEFORE', json.dumps(before, ensure_ascii=False, indent=2))
        # root cause from audit
        # merge all duplicate groups that share labels exactly; current issue all Entity.
        merge_results=[]
        for g in before['duplicateGroups']:
            labels=g['labels']
            if labels == ['Entity']:
                merge_results.append(merge_group(session, g['name'], 'Entity'))
        report['mergeResults']=merge_results
        ensure_exam_nodes(session)
        report['oldQuestionBankLinking']=link_old_question_banks(session)
        after=stats(session); report['after']=after
    driver.close()
    report['finishedAt']=datetime.datetime.now().isoformat()
    path=BASE_DIR/'review_reports'/'kg_audit_repair_20260519_gpt55.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('AFTER', json.dumps(after, ensure_ascii=False, indent=2))
    print('REPORT_PATH', path)

if __name__=='__main__':
    main()
