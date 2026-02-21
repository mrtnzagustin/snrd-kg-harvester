// ============================================================
// SNRD KG Demo Queries
// Run each query separately in Neo4j Browser.
// ============================================================

// 1) Node counts by label
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS total
ORDER BY total DESC;

// 2) Relationship counts by type
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(*) AS total
ORDER BY total DESC;

// 3) Quick visual sample (subgraph)
MATCH (p:Publication)
WITH p ORDER BY rand() LIMIT 20
OPTIONAL MATCH (a:Author)-[:AUTHORED]->(p)
OPTIONAL MATCH (p)-[:IN_REPOSITORY]->(r:Repository)
OPTIONAL MATCH (p)-[:AFFILIATED_WITH]->(i:Institution)
OPTIONAL MATCH (p)-[:HAS_SUBJECT]->(s:Subject)
RETURN p, a, r, i, s;

// 4) Top repositories
MATCH (p:Publication)-[:IN_REPOSITORY]->(r:Repository)
RETURN r.name AS repository, count(*) AS publications
ORDER BY publications DESC
LIMIT 15;

// 5) Top institutions
MATCH (p:Publication)-[:AFFILIATED_WITH]->(i:Institution)
RETURN i.name AS institution, count(*) AS publications
ORDER BY publications DESC
LIMIT 15;

// 6) Top authors
MATCH (a:Author)-[:AUTHORED]->(p:Publication)
RETURN a.name AS author, count(*) AS publications
ORDER BY publications DESC
LIMIT 20;

// 7) Top subjects
MATCH (p:Publication)-[:HAS_SUBJECT]->(s:Subject)
RETURN s.name AS subject, count(*) AS publications
ORDER BY publications DESC
LIMIT 20;

// 8) Publications with most authors
MATCH (a:Author)-[:AUTHORED]->(p:Publication)
RETURN p.id AS publication_id, left(coalesce(p.title, ""), 120) AS title, count(a) AS authors
ORDER BY authors DESC
LIMIT 15;

// 9) Publications with most subjects
MATCH (p:Publication)-[:HAS_SUBJECT]->(s:Subject)
RETURN p.id AS publication_id, left(coalesce(p.title, ""), 120) AS title, count(s) AS subjects
ORDER BY subjects DESC
LIMIT 15;

// 10) Co-authorship network (table)
MATCH (a1:Author)-[:AUTHORED]->(p:Publication)<-[:AUTHORED]-(a2:Author)
WHERE elementId(a1) < elementId(a2)
WITH a1, a2, count(DISTINCT p) AS shared_publications
WHERE shared_publications >= 2
RETURN a1.name AS author_1, a2.name AS author_2, shared_publications
ORDER BY shared_publications DESC
LIMIT 30;

// 11) Co-authorship network (graph)
MATCH (a1:Author)-[:AUTHORED]->(p:Publication)<-[:AUTHORED]-(a2:Author)
WHERE elementId(a1) < elementId(a2)
WITH a1, a2, count(DISTINCT p) AS shared_publications
WHERE shared_publications >= 2
RETURN a1, a2, shared_publications
LIMIT 80;

// 12) Timeline by year parsed from p.date (YYYY...)
MATCH (p:Publication)
WITH substring(coalesce(p.date, ""), 0, 4) AS year
WHERE year =~ "\\d{4}"
RETURN year, count(*) AS publications
ORDER BY year;

// 13) Data quality snapshot
MATCH (p:Publication)
WITH p,
  CASE WHEN EXISTS { MATCH (:Author)-[:AUTHORED]->(p) } THEN 1 ELSE 0 END AS has_author,
  CASE WHEN EXISTS { MATCH (p)-[:IN_REPOSITORY]->(:Repository) } THEN 1 ELSE 0 END AS has_repo,
  CASE WHEN EXISTS { MATCH (p)-[:AFFILIATED_WITH]->(:Institution) } THEN 1 ELSE 0 END AS has_inst,
  CASE WHEN EXISTS { MATCH (p)-[:HAS_SUBJECT]->(:Subject) } THEN 1 ELSE 0 END AS has_subject,
  CASE WHEN EXISTS { MATCH (p)-[:HAS_URL]->(:URL) } THEN 1 ELSE 0 END AS has_url
RETURN
  count(*) AS total_publications,
  sum(1 - has_author) AS without_author,
  sum(1 - has_repo) AS without_repository,
  sum(1 - has_inst) AS without_institution,
  sum(1 - has_subject) AS without_subject,
  sum(1 - has_url) AS without_url;

// 14) Repository x institution matrix
MATCH (p:Publication)-[:IN_REPOSITORY]->(r:Repository)
MATCH (p)-[:AFFILIATED_WITH]->(i:Institution)
RETURN r.name AS repository, i.name AS institution, count(*) AS publications
ORDER BY publications DESC
LIMIT 30;

// 15) Search demo: replace 'salud' with your keyword
MATCH (p:Publication)
WHERE toLower(coalesce(p.title, "")) CONTAINS "salud"
   OR toLower(coalesce(p.description, "")) CONTAINS "salud"
RETURN p.id AS publication_id, left(coalesce(p.title, ""), 160) AS title, p.date AS date
ORDER BY date DESC
LIMIT 25;
