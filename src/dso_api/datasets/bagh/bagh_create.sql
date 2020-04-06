DROP TABLE IF EXISTS bagh_verblijfsobjectpandrelatie;
DROP TABLE IF EXISTS bagh_pand;
DROP TABLE IF EXISTS bagh_nummeraanduiding;
DROP TABLE IF EXISTS bagh_verblijfsobject;
DROP TABLE IF EXISTS bagh_standplaats;
DROP TABLE IF EXISTS bagh_ligplaats;
DROP TABLE IF EXISTS bagh_openbare_ruimte;
DROP TABLE IF EXISTS bagh_woonplaats;
DROP TABLE IF EXISTS bagh_bouwblok;
DROP TABLE IF EXISTS bagh_ggw_praktijkgebied;
DROP TABLE IF EXISTS bagh_buurt;
DROP TABLE IF EXISTS bagh_wijk;
DROP TABLE IF EXISTS bagh_ggw_gebied;
DROP TABLE IF EXISTS bagh_stadsdeel;
DROP TABLE IF EXISTS bagh_gemeente;

CREATE TABLE bagh_gemeente
(
    id character varying(8) PRIMARY KEY,
	identificatie character varying(4) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
    naam character varying(40) NOT NULL,
    verzorgingsgebied boolean
);

CREATE TABLE bagh_stadsdeel
(
    id character varying(18) PRIMARY KEY,
    identificatie character varying(14) NOT NULL,
    volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
	begin_geldigheid date,
    eind_geldigheid date,
    geometrie geometry(MultiPolygon,28992),
    date_modified timestamp with time zone,
    code character varying(3),
    naam character varying(40),
   	documentdatum date,
    documentnummer character varying(100),
    vervallen boolean,
    ingang_cyclus date,
    gemeente_id character varying(18) NOT NULL REFERENCES bagh_gemeente(id)
);

CREATE INDEX ON bagh_stadsdeel USING gist(geometrie);
CREATE INDEX ON bagh_stadsdeel(identificatie);

CREATE TABLE public.bagh_ggw_gebied
(
    id character varying(18) PRIMARY KEY,
	identificatie character varying(14) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
   	documentdatum date,
    documentnummer text,
    code character varying(4) NOT NULL,
    naam text NOT NULL,
    geometrie geometry(MultiPolygon,28992),
    stadsdeel_id character varying(18) NOT NULL REFERENCES bagh_stadsdeel(id)
);

CREATE INDEX ON bagh_ggw_gebied(identificatie);
CREATE INDEX ON bagh_ggw_gebied(code);
CREATE INDEX ON bagh_ggw_gebied USING gist(geometrie);

CREATE TABLE bagh_wijk
(
    id character varying(18) PRIMARY KEY,
	identificatie character varying(14) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
    naam character varying(100) NOT NULL,
    code character varying(3) NOT NULL,
  	documentdatum date,
    documentnummer character varying(100),
	cbs_code character varying(9),
    geometrie geometry(MultiPolygon,28992),
    ggw_gebied_id character varying(18) REFERENCES bagh_ggw_gebied(id),
    stadsdeel_id character varying(18) NOT NULL REFERENCES bagh_stadsdeel(id)
);

CREATE INDEX ON bagh_wijk(identificatie);
CREATE INDEX ON bagh_wijk USING gist(geometrie);

CREATE TABLE bagh_buurt
(
    id character varying(18) PRIMARY KEY,
	identificatie character varying(14) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
    geometrie geometry(MultiPolygon,28992),
    code character varying(4),
    naam text,
    cbs_code character varying(14),
    documentdatum date,
    documentnummer text,
    wijk_id character varying(18) NOT NULL REFERENCES bagh_wijk(id),
    ggw_gebied_id character varying(18) REFERENCES bagh_ggw_gebied(id),
    stadsdeel_id character varying(18) NOT NULL REFERENCES bagh_stadsdeel(id)
);

CREATE INDEX ON bagh_buurt(identificatie);
CREATE INDEX ON bagh_buurt USING gist(geometrie);

CREATE TABLE bagh_ggw_praktijkgebied
(
	id character varying(18) PRIMARY KEY,
	identificatie character varying(14) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
	code character varying(4),
    naam text NOT NULL,
   	documentdatum date,
    documentnummer text,
    geometrie geometry(MultiPolygon,28992),
	stadsdeel_id character varying(18) NOT NULL REFERENCES bagh_stadsdeel(id)
);

CREATE INDEX ON bagh_ggw_praktijkgebied(identificatie);
CREATE INDEX ON bagh_ggw_praktijkgebied USING gist(geometrie);

CREATE TABLE bagh_bouwblok
(
	id character varying(18) PRIMARY KEY,
	identificatie character varying(14) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone NOT NULL,
    begin_geldigheid date,
    eind_geldigheid date,
	code character varying(4) NOT NULL,
	geometrie geometry(MultiPolygon,28992),
    buurt_id character varying(18) REFERENCES bagh_buurt(id)
);

CREATE INDEX ON bagh_bouwblok(identificatie);
CREATE INDEX ON bagh_bouwblok USING gist(geometrie);

CREATE TABLE bagh_woonplaats
(
    id character varying(8) PRIMARY KEY,
	identificatie character varying(4) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
	aanduiding_in_onderzoek boolean,
	geconstateerd boolean,
    naam character varying(40) NOT NULL,
	documentdatum date,
    documentnummer text,
	status text NOT NULL,
	geometrie geometry(MultiPolygon,28992),
	gemeente_id character varying(8) REFERENCES bagh_gemeente(id)
);

CREATE INDEX ON bagh_woonplaats(identificatie);
CREATE INDEX ON bagh_woonplaats USING gist(geometrie);

CREATE TABLE bagh_openbare_ruimte
(
	id character varying(20) PRIMARY KEY,
	identificatie character varying(16) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
	aanduiding_in_onderzoek boolean,
	geconstateerd boolean,
    naam text NOT NULL,
    naam_nen text NOT NULL,
	type text,
    documentdatum date,
    documentnummer text,
    status text NOT NULL,
	geometrie geometry(MultiPolygon,28992),
	woonplaats_id character varying(12) REFERENCES bagh_woonplaats(id)
);

CREATE INDEX ON bagh_openbare_ruimte(identificatie);
CREATE INDEX ON bagh_openbare_ruimte USING gist(geometrie);

CREATE TABLE bagh_ligplaats
(
	id character varying(20) PRIMARY KEY,
	identificatie character varying(16) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
   	documentdatum date,
    documentnummer character varying(100),
	aanduiding_in_onderzoek boolean,
	geconstateerd boolean,
	hoofdadres_id character varying(20) NOT NULL,
    geometrie geometry(Polygon,28992),
	status text NOT NULL,
	buurt_id character varying(18) NOT NULL REFERENCES bagh_buurt(id)
);

CREATE INDEX ON bagh_ligplaats(identificatie);
CREATE INDEX ON bagh_ligplaats USING gist(geometrie);

CREATE TABLE bagh_standplaats
(
	id character varying(20) PRIMARY KEY,
	identificatie character varying(16) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
   	documentdatum date,
    documentnummer character varying(100),
	aanduiding_in_onderzoek boolean,
	geconstateerd boolean,
	hoofdadres_id character varying(20) NOT NULL,
    geometrie geometry(Polygon,28992),
	status text NOT NULL,
	buurt_id character varying(18) REFERENCES bagh_buurt(id)
);

CREATE INDEX ON bagh_standplaats(identificatie);
CREATE INDEX ON bagh_standplaats USING gist(geometrie);

CREATE TABLE bagh_verblijfsobject
(
	id character varying(20) PRIMARY KEY,
	identificatie character varying(16) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
   	documentdatum date,
    documentnummer character varying(100),
	aanduiding_in_onderzoek boolean,
	geconstateerd boolean,
	heeftin_hoofdadres_id character varying(20) NOT NULL,
	heeftin_nevenadres_id character varying(20) [],
    geometrie geometry(Point,28992),
    oppervlakte integer,
	status text NOT NULL,
    verdieping_toegang integer,
    aantal_eenheden_complex integer,
    aantal_bouwlagen integer,
    hoogste_bouwlaag integer,
    laagste_bouwlaag integer,
    aantal_kamers integer,
    eigendomsverhouding text,
    gebruiksdoel_gezondheidszorgfunctie text,
    gebruiksdoel_woonfunctie text,
    gebruik text,
    gebruiksdoel text[] NOT NULL,
    toegang text[] NOT NULL,
    redenopvoer text,
    redenafvoer text,
	buurt_id character varying(18) REFERENCES bagh_buurt(id)
);

CREATE INDEX ON bagh_verblijfsobject(identificatie);
CREATE INDEX ON bagh_verblijfsobject USING gist(geometrie);

CREATE TABLE bagh_nummeraanduiding
(
	id character varying(20) PRIMARY KEY,
	identificatie character varying(16) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
   	documentdatum date,
    documentnummer character varying(100),
	aanduiding_in_onderzoek boolean,
	geconstateerd boolean,
    huisnummer integer NOT NULL,
    huisletter character varying(1),
    huisnummer_toevoeging character varying(4),
    postcode character varying(6),
    openbare_ruimte_id character varying(20) REFERENCES bagh_openbare_ruimte(id),
    ligplaats_id character varying(20) REFERENCES bagh_ligplaats(id),
    standplaats_id character varying(20) REFERENCES bagh_standplaats(id),
    verblijfsobject_id character varying(20) REFERENCES bagh_verblijfsobject(id),
	type_adres text,
	status text
);

CREATE INDEX ON bagh_nummeraanduiding(identificatie);

CREATE TABLE bagh_pand
(
	id character varying(20) PRIMARY KEY,
	identificatie character varying(16) NOT NULL,
	volgnummer smallint NOT NULL,
	registratiedatum timestamp with time zone,
    begin_geldigheid date,
    eind_geldigheid date,
   	documentdatum date,
    documentnummer character varying(100),
	aanduiding_in_onderzoek boolean,
    geconstateerd boolean,
    bouwjaar integer CHECK (bouwjaar >= 0),
	status text NOT NULL,
	naam text,
	ligging text,
	type_woonobject text,
	aantal_bouwlagen integer CHECK (aantal_bouwlagen >= 0),
    laagste_bouwlaag integer,
    hoogste_bouwlaag integer,
    geometrie geometry(Polygon,28992),
    bouwblok_id character varying(18) REFERENCES bagh_bouwblok(id)
);

CREATE INDEX ON bagh_pand(identificatie);
CREATE INDEX ON bagh_pand USING gist(geometrie);

CREATE TABLE bagh_verblijfsobjectpandrelatie
(
    id character varying(41) PRIMARY KEY,
    pand_id character varying(20) NOT NULL REFERENCES bagh_pand(id),
    verblijfsobject_id character varying(20) NOT NULL REFERENCES bagh_verblijfsobject(id)
);

CREATE INDEX ON bagh_verblijfsobjectpandrelatie(pand_id);
CREATE INDEX ON bagh_verblijfsobjectpandrelatie(verblijfsobject_id);

