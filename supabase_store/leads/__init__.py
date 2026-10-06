from supabase_store.leads.changes import ChangeMixin
from supabase_store.leads.records import RecordMixin
from supabase_store.transcripts import TranscriptMixin


class SupabaseCRMStore(ChangeMixin, RecordMixin, TranscriptMixin):
    pass
