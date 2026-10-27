-- Исходные объекты OSM, как их отдал Overpass
CREATE TABLE IF NOT EXISTS osm_objects (
    osm_type  VARCHAR  NOT NULL CHECK (osm_type IN ('node', 'way', 'relation')),
    osm_id    BIGINT   NOT NULL,
    tags      JSON     NOT NULL,
    geom      GEOMETRY NOT NULL,
    region    VARCHAR  NOT NULL,
    loaded_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (osm_type, osm_id)
);

-- Результат классификации: одна строка на пару (объект, домен)
CREATE TABLE IF NOT EXISTS osm_classification (
    osm_type      VARCHAR NOT NULL,
    osm_id        BIGINT  NOT NULL,
    domain        VARCHAR NOT NULL CHECK (domain IN ('money', 'labor', 'goods')),
    role          VARCHAR NOT NULL CHECK (role IN ('supply', 'demand')),
    kind          VARCHAR NOT NULL,
    rule          VARCHAR,
    classified_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (osm_type, osm_id, domain)
);

-- Таблицы из schema.md
CREATE TABLE IF NOT EXISTS districts (
    id   VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    geom GEOMETRY
);

CREATE TABLE IF NOT EXISTS subjects (
    id          VARCHAR PRIMARY KEY,
    name        VARCHAR,
    kind        VARCHAR NOT NULL,
    lon         DOUBLE  NOT NULL,
    lat         DOUBLE  NOT NULL,
    address     VARCHAR,
    district_id VARCHAR,
    osm_type    VARCHAR,
    osm_id      BIGINT
);

CREATE TABLE IF NOT EXISTS capacities (
    subject_id VARCHAR NOT NULL,
    domain     VARCHAR NOT NULL CHECK (domain IN ('money', 'labor', 'goods')),
    role       VARCHAR NOT NULL CHECK (role IN ('supply', 'demand')),
    capacity   DOUBLE  NOT NULL CHECK (capacity > 0),
    PRIMARY KEY (subject_id, domain)
);

CREATE TABLE IF NOT EXISTS edges (
    id          VARCHAR PRIMARY KEY,
    domain      VARCHAR NOT NULL CHECK (domain IN ('money', 'labor', 'goods')),
    from_id     VARCHAR NOT NULL,
    to_id       VARCHAR NOT NULL,
    distance_km DOUBLE  NOT NULL,
    weight      DOUBLE  NOT NULL CHECK (weight > 0 AND weight <= 1)
);

CREATE TABLE IF NOT EXISTS metrics (
    scope       VARCHAR NOT NULL CHECK (scope IN ('district', 'region')),
    district_id VARCHAR,
    domain      VARCHAR NOT NULL,
    node_count  INTEGER NOT NULL,
    edge_count  INTEGER NOT NULL,
    avg_degree  DOUBLE  NOT NULL,
    low_data    BOOLEAN NOT NULL
);