{{ config(materialized='table') }}

WITH latest as 
(select
  customer_id,
  first_name,
  last_name,
  email,
  created_at,
  dbt_valid_from AS effective_from,
  dbt_valid_to AS effective_to,
  CASE WHEN dbt_valid_to IS NULL THEN TRUE ELSE FALSE END AS is_current
from {{ ref('customers_snapshot') }}
) 

select * from latest