from crm_store.leads.records import RecordMixin
from crm_store.leads.storage import StorageMixin


class CRMStore(RecordMixin, StorageMixin):
    pass
