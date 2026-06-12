"""Tests del feature de API keys: modelo, autenticación, ámbito, UI y docs."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.enums import ApiKeyScope
from apps.core.models import ApiKey, ApiKeyUsage
from apps.teams.models import Team

User = get_user_model()


class ApiKeyModelTests(TestCase):
    def test_generate_returns_raw_once_and_verifies(self):
        owner = User.objects.create_user(email="o@x.com", password="p", is_owner=True)
        obj, raw = ApiKey.generate(name="k", scope=ApiKeyScope.FULL, user=owner)
        self.assertTrue(raw.startswith("cf_live_"))
        self.assertNotIn(raw, (obj.hashed_key,))          # no se guarda en claro
        self.assertEqual(ApiKey.lookup(raw), obj)         # se verifica por hash
        self.assertIsNone(ApiKey.lookup("cf_live_invalida"))

    def test_read_only_prefix(self):
        owner = User.objects.create_user(email="o2@x.com", password="p", is_owner=True)
        obj, raw = ApiKey.generate(name="ro", scope=ApiKeyScope.READ_ONLY, user=owner)
        self.assertTrue(raw.startswith("cf_ro_"))
        self.assertTrue(obj.is_read_only)


class ApiKeyAuthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(email="owner@x.com", password="p", is_owner=True)
        cls.team = Team.objects.create(name="G")
        _, cls.full = ApiKey.generate(name="full", scope=ApiKeyScope.FULL, user=cls.owner)
        _, cls.ro = ApiKey.generate(name="ro", scope=ApiKeyScope.READ_ONLY, user=cls.owner)

    def test_no_key_unauthorized(self):
        self.assertEqual(self.client.get("/api/certificates/").status_code, 401)

    def test_invalid_key_unauthorized(self):
        r = self.client.get("/api/certificates/", HTTP_AUTHORIZATION="Api-Key nope")
        self.assertEqual(r.status_code, 401)

    def test_full_key_can_read(self):
        r = self.client.get("/api/certificates/", HTTP_AUTHORIZATION=f"Api-Key {self.full}")
        self.assertEqual(r.status_code, 200)

    def test_x_api_key_header_works(self):
        r = self.client.get("/api/certificates/", HTTP_X_API_KEY=self.full)
        self.assertEqual(r.status_code, 200)

    def test_read_only_key_cannot_write(self):
        r = self.client.post(
            "/api/certificates/",
            data={"domain": "a.com", "port": 443, "team": self.team.id},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Api-Key {self.ro}",
        )
        self.assertEqual(r.status_code, 403)

    def test_last_used_updates(self):
        key = ApiKey.lookup(self.full)
        self.assertIsNone(key.last_used_at)
        self.client.get("/api/certificates/", HTTP_AUTHORIZATION=f"Api-Key {self.full}")
        key.refresh_from_db()
        self.assertIsNotNone(key.last_used_at)


class ApiKeyProvisioningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(email="ow@x.com", password="p", is_owner=True)
        cls.member = User.objects.create_user(email="m@x.com", password="p")

    def test_non_owner_forbidden(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("api-keys")).status_code, 403)

    def test_owner_can_list(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("api-keys"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "/api")  # muestra la URL base

    def test_create_shows_raw_key_once(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("api-key-create"), {"name": "Teams", "scope": "full"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "cf_live_")          # secreto mostrado una vez
        self.assertContains(r, "Authorization: Api-Key")
        self.assertEqual(ApiKey.objects.count(), 1)

    def test_revoke_deactivates(self):
        self.client.force_login(self.owner)
        obj, _ = ApiKey.generate(name="k", scope=ApiKeyScope.FULL, user=self.owner)
        r = self.client.post(reverse("api-key-revoke", args=[obj.pk]))
        self.assertEqual(r.status_code, 200)
        obj.refresh_from_db()
        self.assertFalse(obj.is_active)

    def test_docs_page_authenticated(self):
        self.client.force_login(self.member)
        r = self.client.get(reverse("api-docs"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Api-Key")


class ApiKeyUsageViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(email="ow2@x.com", password="p", is_owner=True)
        cls.member = User.objects.create_user(email="m2@x.com", password="p")
        cls.key, _ = ApiKey.generate(name="k", scope=ApiKeyScope.FULL, user=cls.owner)
        cls.other, _ = ApiKey.generate(name="other", scope=ApiKeyScope.READ_ONLY, user=cls.owner)
        ApiKeyUsage.objects.create(
            api_key=cls.key, method="GET", path="/api/certificates/",
            status_code=200, ip="10.0.0.7",
        )
        ApiKeyUsage.objects.create(
            api_key=cls.key, method="POST", path="/api/certificates/",
            status_code=201, ip="10.0.0.8",
        )
        ApiKeyUsage.objects.create(
            api_key=cls.other, method="GET", path="/api/alerts/",
            status_code=200, ip="10.0.0.9",
        )

    def test_owner_sees_usage_rows(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("api-key-usage", args=[self.key.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Registro de uso")
        self.assertContains(r, "forge-modal__panel")
        self.assertContains(r, "10.0.0.7")
        self.assertContains(r, "10.0.0.8")

    def test_usage_lists_only_this_keys_rows(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("api-key-usage", args=[self.key.pk]))
        self.assertContains(r, "/api/certificates/")
        self.assertNotContains(r, "10.0.0.9")          # uso de OTRA clave
        self.assertEqual(len(r.context["usages"]), 2)

    def test_usage_most_recent_first(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("api-key-usage", args=[self.key.pk]))
        usages = list(r.context["usages"])
        ats = [u.at for u in usages]
        self.assertEqual(ats, sorted(ats, reverse=True))  # más recientes primero

    def test_non_owner_forbidden(self):
        self.client.force_login(self.member)
        r = self.client.get(reverse("api-key-usage", args=[self.key.pk]))
        self.assertEqual(r.status_code, 403)

    def test_anonymous_redirected(self):
        r = self.client.get(reverse("api-key-usage", args=[self.key.pk]))
        self.assertIn(r.status_code, (301, 302))

    def test_unknown_key_404(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("api-key-usage", args=[999999]))
        self.assertEqual(r.status_code, 404)

    def test_list_row_has_usage_button(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("api-keys"))
        self.assertContains(r, reverse("api-key-usage", args=[self.key.pk]))
        self.assertContains(r, 'hx-target="#modal-root"')
        self.assertContains(r, "Ver uso")
