"""Bounded PubMed retrieval; only fixed official hosts are contacted."""
import hashlib
import os
import xml.etree.ElementTree as ET

import httpx
from fastapi import HTTPException


async def search(query, limit=3):
    params = {'db': 'pubmed', 'term': query, 'retmode': 'json', 'retmax': min(limit, 5),
        'sort': 'pub date', 'tool': 'lianban-research'}
    if os.environ.get('NCBI_API_KEY'):
        params['api_key'] = os.environ['NCBI_API_KEY']
    if os.environ.get('NCBI_CONTACT_EMAIL'):
        params['email'] = os.environ['NCBI_CONTACT_EMAIL']
    base = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10)) as client:
            found = await client.get(base + 'esearch.fcgi', params=params)
            found.raise_for_status()
            ids = found.json()['esearchresult']['idlist']
            if not ids:
                return []
            if any(not str(i).isdigit() for i in ids):
                raise ValueError('Invalid PubMed IDs')
            result = await client.get(base + 'efetch.fcgi', params={**params, 'retmode': 'xml', 'id': ','.join(ids)})
            result.raise_for_status()
            if len(result.content) > 2_000_000 or b'<!ENTITY' in result.content:
                raise ValueError('Unexpected literature payload')
            root = ET.fromstring(result.content)
        documents = []
        for article in root.findall('.//PubmedArticle')[:limit]:
            pmid = article.findtext('.//MedlineCitation/PMID', '')
            if not pmid.isdigit():
                continue
            title = ''.join(article.find('.//ArticleTitle').itertext())
            abstract = '\n'.join(''.join(p.itertext()) for p in article.findall('.//Abstract/AbstractText'))[:20000]
            doi = next((a.text for a in article.findall('.//ArticleId') if a.get('IdType') == 'doi'), None)
            types = [a.text for a in article.findall('.//PublicationType') if a.text]
            retracted = any('retract' in t.lower() for t in types) or bool(article.findall('.//CommentsCorrections[@RefType="RetractionIn"]'))
            value = {'pmid': pmid, 'doi': doi, 'title': title[:600], 'abstract': abstract,
                'url': 'https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/', 'publication_types': types,
                'year': article.findtext('.//JournalIssue/PubDate/Year', ''),
                'text_scope': 'abstract_only', 'retraction_detected': retracted,
                'correction_status': 'flags_in_current_pubmed_record_only',
                'license': 'publisher_terms_not_assumed_open_access'}
            value['source_hash'] = hashlib.sha256((title + '\n' + abstract + str(types)).encode()).hexdigest()
            value['id'] = 'pmid-' + pmid + '-' + value['source_hash'][:12]
            documents.append(value)
        return documents
    except (httpx.HTTPError, ET.ParseError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(502, 'PubMed检索暂不可用；未导入不完整的文献记录') from None
