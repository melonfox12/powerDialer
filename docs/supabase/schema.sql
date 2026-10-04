create table if not exists public.prospects (
    id text primary key,
    user_id uuid,
    data jsonb not null check (jsonb_typeof(data) = 'object')
);

create table if not exists public.dialer_metric_daily (
    user_id uuid not null default '00000000-0000-0000-0000-000000000000',
    day date not null,
    metric_key text not null check (
        metric_key in (
            'booked', 'call_later', 'connected', 'disqualified', 'interested',
            'dials', 'failed', 'talk_seconds', 'voicemail'
        )
    ),
    value bigint not null default 0 check (value >= 0),
    primary key (user_id, day, metric_key)
);

create table if not exists public.dialer_metric_totals (
    user_id uuid not null default '00000000-0000-0000-0000-000000000000',
    metric_key text not null check (
        metric_key in (
            'booked', 'call_later', 'connected', 'disqualified', 'interested',
            'dials', 'failed', 'talk_seconds', 'voicemail'
        )
    ),
    value bigint not null default 0 check (value >= 0),
    primary key (user_id, metric_key)
);

create table if not exists public.dialer_sessions (
    id text primary key,
    user_id uuid,
    started_at timestamptz not null,
    ended_at timestamptz,
    data jsonb not null check (jsonb_typeof(data) = 'object')
);

alter table public.dialer_metric_daily
    drop constraint if exists dialer_metric_daily_metric_key_check;
alter table public.dialer_metric_daily
    add constraint dialer_metric_daily_metric_key_check check (
        metric_key in (
            'booked', 'call_later', 'connected', 'disqualified', 'interested',
            'dials', 'failed', 'talk_seconds', 'voicemail'
        )
    );
alter table public.dialer_metric_totals
    drop constraint if exists dialer_metric_totals_metric_key_check;
alter table public.dialer_metric_totals
    add constraint dialer_metric_totals_metric_key_check check (
        metric_key in (
            'booked', 'call_later', 'connected', 'disqualified', 'interested',
            'dials', 'failed', 'talk_seconds', 'voicemail'
        )
    );

alter table public.prospects enable row level security;
alter table public.dialer_metric_daily enable row level security;
alter table public.dialer_metric_totals enable row level security;
alter table public.dialer_sessions enable row level security;

create table if not exists public.dialer_settings (
    id text primary key,
    data jsonb not null check (jsonb_typeof(data) = 'object')
);

alter table public.dialer_settings enable row level security;

revoke all on public.prospects from public, anon, authenticated;
revoke all on public.dialer_metric_daily from public, anon, authenticated;
revoke all on public.dialer_metric_totals from public, anon, authenticated;
revoke all on public.dialer_sessions from public, anon, authenticated;
revoke all on public.dialer_settings from public, anon, authenticated;
grant all on public.prospects to service_role;
grant all on public.dialer_metric_daily to service_role;
grant all on public.dialer_metric_totals to service_role;
grant all on public.dialer_sessions to service_role;
grant all on public.dialer_settings to service_role;

alter table public.prospects add column if not exists user_id uuid;
alter table public.dialer_sessions add column if not exists user_id uuid;
alter table public.dialer_metric_daily add column if not exists user_id uuid;
alter table public.dialer_metric_totals add column if not exists user_id uuid;
update public.dialer_metric_daily set user_id = '00000000-0000-0000-0000-000000000000' where user_id is null;
update public.dialer_metric_totals set user_id = '00000000-0000-0000-0000-000000000000' where user_id is null;
alter table public.dialer_metric_daily alter column user_id set default '00000000-0000-0000-0000-000000000000';
alter table public.dialer_metric_totals alter column user_id set default '00000000-0000-0000-0000-000000000000';
alter table public.dialer_metric_daily drop constraint if exists dialer_metric_daily_pkey;
alter table public.dialer_metric_totals drop constraint if exists dialer_metric_totals_pkey;
alter table public.dialer_metric_daily add primary key (user_id, day, metric_key);
alter table public.dialer_metric_totals add primary key (user_id, metric_key);

create index if not exists prospects_user_id_idx on public.prospects (user_id);
create index if not exists dialer_sessions_user_id_idx on public.dialer_sessions (user_id);

drop policy if exists prospects_own on public.prospects;
drop policy if exists dialer_metric_daily_own on public.dialer_metric_daily;
drop policy if exists dialer_metric_totals_own on public.dialer_metric_totals;
drop policy if exists dialer_sessions_own on public.dialer_sessions;
drop policy if exists dialer_settings_own on public.dialer_settings;
create policy prospects_own on public.prospects for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy dialer_metric_daily_own on public.dialer_metric_daily for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy dialer_metric_totals_own on public.dialer_metric_totals for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy dialer_sessions_own on public.dialer_sessions for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy dialer_settings_own on public.dialer_settings for all to authenticated using (id = auth.uid()::text) with check (id = auth.uid()::text);

grant select, insert, update, delete on public.prospects to authenticated;
grant select, insert, update, delete on public.dialer_metric_daily to authenticated;
grant select, insert, update, delete on public.dialer_metric_totals to authenticated;
grant select, insert, update, delete on public.dialer_sessions to authenticated;
grant select, insert, update, delete on public.dialer_settings to authenticated;

drop function if exists public.increment_dialer_metric(text, integer);
drop function if exists public.increment_dialer_metric(text, integer, uuid);
create or replace function public.increment_dialer_metric(metric_key text, increment_by integer, for_user uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if for_user is null then
        raise exception 'A user is required to increment dialer metrics';
    end if;
    if metric_key not in (
        'booked', 'call_later', 'connected', 'disqualified', 'interested',
        'dials', 'failed', 'talk_seconds', 'voicemail'
    ) then
        raise exception 'Unknown dialer metric';
    end if;
    if increment_by <= 0 then
        raise exception 'Metric increment must be positive';
    end if;

    insert into public.dialer_metric_daily as daily (user_id, day, metric_key, value)
    values (for_user, timezone('utc', now())::date, metric_key, increment_by)
    on conflict (user_id, day, metric_key)
    do update set value = daily.value + excluded.value;

    insert into public.dialer_metric_totals as totals (user_id, metric_key, value)
    values (for_user, metric_key, increment_by)
    on conflict (user_id, metric_key)
    do update set value = totals.value + excluded.value;
end;
$$;

revoke all on function public.increment_dialer_metric(text, integer, uuid) from public, anon, authenticated;
grant execute on function public.increment_dialer_metric(text, integer, uuid) to service_role;
