create table if not exists public.prospects (
    id text primary key,
    data jsonb not null check (jsonb_typeof(data) = 'object')
);

create table if not exists public.dialer_metric_daily (
    day date not null,
    metric_key text not null check (
        metric_key in (
            'booked', 'call_later', 'connected', 'disqualified',
            'dials', 'failed', 'talk_seconds', 'voicemail'
        )
    ),
    value bigint not null default 0 check (value >= 0),
    primary key (day, metric_key)
);

create table if not exists public.dialer_metric_totals (
    metric_key text primary key check (
        metric_key in (
            'booked', 'call_later', 'connected', 'disqualified',
            'dials', 'failed', 'talk_seconds', 'voicemail'
        )
    ),
    value bigint not null default 0 check (value >= 0)
);

create table if not exists public.dialer_sessions (
    id text primary key,
    started_at timestamptz not null,
    ended_at timestamptz,
    data jsonb not null check (jsonb_typeof(data) = 'object')
);

alter table public.prospects enable row level security;
alter table public.dialer_metric_daily enable row level security;
alter table public.dialer_metric_totals enable row level security;
alter table public.dialer_sessions enable row level security;

revoke all on public.prospects from public, anon, authenticated;
revoke all on public.dialer_metric_daily from public, anon, authenticated;
revoke all on public.dialer_metric_totals from public, anon, authenticated;
revoke all on public.dialer_sessions from public, anon, authenticated;
grant all on public.prospects to service_role;
grant all on public.dialer_metric_daily to service_role;
grant all on public.dialer_metric_totals to service_role;
grant all on public.dialer_sessions to service_role;

create or replace function public.increment_dialer_metric(metric_key text, increment_by integer)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if metric_key not in (
        'booked', 'call_later', 'connected', 'disqualified',
        'dials', 'failed', 'talk_seconds', 'voicemail'
    ) then
        raise exception 'Unknown dialer metric';
    end if;
    if increment_by <= 0 then
        raise exception 'Metric increment must be positive';
    end if;

    insert into public.dialer_metric_daily as daily (day, metric_key, value)
    values (timezone('utc', now())::date, metric_key, increment_by)
    on conflict (day, metric_key)
    do update set value = daily.value + excluded.value;

    insert into public.dialer_metric_totals as totals (metric_key, value)
    values (metric_key, increment_by)
    on conflict (metric_key)
    do update set value = totals.value + excluded.value;
end;
$$;

revoke all on function public.increment_dialer_metric(text, integer) from public, anon, authenticated;
grant execute on function public.increment_dialer_metric(text, integer) to service_role;
