"""產生要貼進 Supabase SQL Editor 的設定。
usage: python3 -I supabase_setup.py <data.json|-> <family_code> > setup.sql
  data 給 "-" 表示不帶起始資料：雲端先空著，第一支有紀錄的手機連上時會自動上傳當起點。
- 建 ly_cfg / ly_snap / ly_ops 三張表，全部開 RLS 且不給任何 policy（anon 不能直接讀寫）。
- 只開放四個 security definer 函式，每個都要帶家庭代碼 p_k。
- 用 data.json 當雲端起始資料（ly_snap）。重跑會「重設」雲端資料並清掉舊 op。
這個輸出含有寶寶紀錄與家庭代碼，不要 commit。
"""
import sys, json

data = None if sys.argv[1] == '-' else json.load(open(sys.argv[1], encoding='utf8'))
code = sys.argv[2]
assert len(code) >= 20 and code.replace('-', '').replace('_', '').isalnum()
body = json.dumps(data, ensure_ascii=False, separators=(',', ':')) if data is not None else ''
tag = '$lydata$'
assert tag not in body

print(f"""-- 淩淵 App 雲端同步設定（整段貼上後按 Run）
create table if not exists public.ly_cfg (id int primary key default 1 check (id = 1), k text not null);
create table if not exists public.ly_snap (id int primary key default 1 check (id = 1), data jsonb not null, seq bigint not null default 0, at timestamptz not null default now());
create table if not exists public.ly_ops (seq bigserial primary key, op jsonb not null, by text, at timestamptz not null default now());
alter table public.ly_cfg enable row level security;
alter table public.ly_snap enable row level security;
alter table public.ly_ops enable row level security;
revoke all on public.ly_cfg, public.ly_snap, public.ly_ops from anon, authenticated;

create or replace function public.ly_check(p_k text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if p_k is null or not exists (select 1 from ly_cfg where k = p_k) then
    raise exception 'bad_key' using errcode = '28000';
  end if;
end $$;

create or replace function public.ly_pull(p_k text, p_after bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
declare s_data jsonb; s_seq bigint; from_seq bigint; o jsonb; mx bigint;
begin
  perform ly_check(p_k);
  select data, seq into s_data, s_seq from ly_snap where id = 1;
  if s_data is null then
    return jsonb_build_object('empty', true);
  end if;
  from_seq := case when p_after < s_seq then s_seq else p_after end;
  select coalesce(jsonb_agg(op order by seq), '[]'::jsonb), max(seq) into o, mx
    from (select seq, op from ly_ops where seq > from_seq order by seq limit 5000) t;
  return jsonb_build_object('seq', coalesce(mx, from_seq), 'ops', o)
      || case when p_after < s_seq then jsonb_build_object('snap', s_data) else '{{}}'::jsonb end;
end $$;

create or replace function public.ly_push(p_k text, p_ops jsonb, p_by text default '') returns bigint
language plpgsql security definer set search_path = public as $$
declare mx bigint;
begin
  perform ly_check(p_k);
  if jsonb_typeof(p_ops) <> 'array' or jsonb_array_length(p_ops) > 200 or length(p_ops::text) > 200000 then
    raise exception 'bad_ops';
  end if;
  insert into ly_ops (op, by) select e, left(coalesce(p_by, ''), 40) from jsonb_array_elements(p_ops) e;
  select max(seq) into mx from ly_ops;
  return mx;
end $$;

create or replace function public.ly_init(p_k text, p_data jsonb) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  perform ly_check(p_k);
  insert into ly_snap (id, data, seq) values (1, p_data, nextval(pg_get_serial_sequence('public.ly_ops', 'seq')))
    on conflict (id) do nothing;
  return true;
end $$;

revoke all on function public.ly_check(text) from public, anon, authenticated;
revoke all on function public.ly_pull(text, bigint), public.ly_push(text, jsonb, text), public.ly_init(text, jsonb) from public;
grant execute on function public.ly_pull(text, bigint), public.ly_push(text, jsonb, text), public.ly_init(text, jsonb) to anon, authenticated;

-- 家庭代碼（重跑會換代碼）
insert into public.ly_cfg (id, k) values (1, '{code}') on conflict (id) do update set k = excluded.k;
""")
if data is not None:
    print(f"""-- 起始資料（重跑會重設雲端資料）
delete from public.ly_ops;
insert into public.ly_snap (id, data, seq) values (1, {tag}{body}{tag}::jsonb, nextval(pg_get_serial_sequence('public.ly_ops', 'seq')))
  on conflict (id) do update set data = excluded.data, seq = excluded.seq, at = now();

select 'OK：雲端已設定，紀錄 ' || jsonb_array_length(data->'logs') || ' 筆' as 結果 from public.ly_snap;
""")
else:
    print("select 'OK：雲端已設定（尚無資料，等第一支手機上傳）' as 結果;")
