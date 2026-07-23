"""FHIR R4 mapping package (v2).

Hand-built FHIR: every resource is a plain Python dict serialized with stdlib
``json`` — keeping the project's zero-runtime-dependency principle. One mapper
module per FHIR resource (``map_claim`` for 837, later ``map_eob`` for 835, …),
each exposing ``to_fhir(dict) -> list[resource dicts]``. ``writer`` dispatches
by transaction type and assembles the FHIR Bundle.

See docx/v2/ for the design and mapping reference.
"""
