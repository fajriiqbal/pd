from django.db import models


class SchoolIdentity(models.Model):
    institution_name = models.CharField(max_length=150, verbose_name="Nama madrasah")
    npsn = models.CharField(max_length=20, verbose_name="NPSN")
    nsm = models.CharField(max_length=30, blank=True, verbose_name="NSM")
    legal_name = models.CharField(max_length=150, blank=True, verbose_name="Nama legal")
    address = models.CharField(max_length=255, verbose_name="Alamat")
    village = models.CharField(max_length=100, blank=True, verbose_name="Desa / Kelurahan")
    district = models.CharField(max_length=100, verbose_name="Kecamatan")
    regency = models.CharField(max_length=100, verbose_name="Kabupaten / Kota")
    province = models.CharField(max_length=100, verbose_name="Provinsi")
    postal_code = models.CharField(max_length=10, blank=True, verbose_name="Kode pos")
    phone_number = models.CharField(max_length=20, blank=True, verbose_name="Telepon")
    email = models.EmailField(blank=True, verbose_name="Email")
    website = models.URLField(blank=True, verbose_name="Situs web")
    principal_name = models.CharField(max_length=150, verbose_name="Nama kepala madrasah")
    principal_nip = models.CharField(max_length=30, verbose_name="NIP kepala madrasah")
    operator_name = models.CharField(max_length=150, blank=True, verbose_name="Nama operator")
    operator_phone = models.CharField(max_length=20, blank=True, verbose_name="Nomor operator")
    letter_footer = models.CharField(max_length=255, blank=True, verbose_name="Catatan footer surat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Identitas Madrasah"
        verbose_name_plural = "Identitas Madrasah"

    def __str__(self) -> str:
        return self.institution_name

    def save(self, *args, **kwargs):
        if not self.pk:
            existing = type(self).objects.first()
            if existing:
                self.pk = existing.pk
        super().save(*args, **kwargs)

    @property
    def is_complete(self) -> bool:
        required_values = [
            self.institution_name,
            self.npsn,
            self.address,
            self.district,
            self.regency,
            self.province,
            self.principal_name,
            self.principal_nip,
        ]
        return all(bool(value and str(value).strip()) for value in required_values)

    @property
    def full_address(self) -> str:
        parts = [self.address, self.village, self.district, self.regency, self.province]
        return ", ".join(part for part in parts if part)

