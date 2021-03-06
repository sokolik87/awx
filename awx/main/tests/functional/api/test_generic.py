import pytest

from awx.api.versioning import reverse


@pytest.mark.django_db
def test_proxy_ip_whitelist(get, patch, admin):
    url = reverse('api:setting_singleton_detail', kwargs={'category_slug': 'system'})
    patch(url, user=admin, data={
        'REMOTE_HOST_HEADERS': [
            'HTTP_X_FROM_THE_LOAD_BALANCER',
            'REMOTE_ADDR',
            'REMOTE_HOST'
        ]
    })

    class HeaderTrackingMiddleware(object):
        environ = {}

        def process_request(self, request):
            pass

        def process_response(self, request, response):
            self.environ = request.environ

    # By default, `PROXY_IP_WHITELIST` is disabled, so custom `REMOTE_HOST_HEADERS`
    # should just pass through
    middleware = HeaderTrackingMiddleware()
    get(url, user=admin, middleware=middleware,
        HTTP_X_FROM_THE_LOAD_BALANCER='some-actual-ip')
    assert middleware.environ['HTTP_X_FROM_THE_LOAD_BALANCER'] == 'some-actual-ip'

    # If `PROXY_IP_WHITELIST` is restricted to 10.0.1.100 and we make a request
    # from 8.9.10.11, the custom `HTTP_X_FROM_THE_LOAD_BALANCER` header should
    # be stripped
    patch(url, user=admin, data={
        'PROXY_IP_WHITELIST': ['10.0.1.100']
    })
    middleware = HeaderTrackingMiddleware()
    get(url, user=admin, middleware=middleware, REMOTE_ADDR='8.9.10.11',
        HTTP_X_FROM_THE_LOAD_BALANCER='some-actual-ip')
    assert 'HTTP_X_FROM_THE_LOAD_BALANCER' not in middleware.environ

    # If 8.9.10.11 is added to `PROXY_IP_WHITELIST` the
    # `HTTP_X_FROM_THE_LOAD_BALANCER` header should be passed through again
    patch(url, user=admin, data={
        'PROXY_IP_WHITELIST': ['10.0.1.100', '8.9.10.11']
    })
    middleware = HeaderTrackingMiddleware()
    get(url, user=admin, middleware=middleware, REMOTE_ADDR='8.9.10.11',
        HTTP_X_FROM_THE_LOAD_BALANCER='some-actual-ip')
    assert middleware.environ['HTTP_X_FROM_THE_LOAD_BALANCER'] == 'some-actual-ip'

    # Allow whitelisting of proxy hostnames in addition to IP addresses
    patch(url, user=admin, data={
        'PROXY_IP_WHITELIST': ['my.proxy.example.org']
    })
    middleware = HeaderTrackingMiddleware()
    get(url, user=admin, middleware=middleware, REMOTE_ADDR='8.9.10.11',
        REMOTE_HOST='my.proxy.example.org',
        HTTP_X_FROM_THE_LOAD_BALANCER='some-actual-ip')
    assert middleware.environ['HTTP_X_FROM_THE_LOAD_BALANCER'] == 'some-actual-ip'


@pytest.mark.django_db
class TestDeleteViews:
    def test_sublist_delete_permission_check(self, inventory_source, host, rando, delete):
        inventory_source.hosts.add(host)
        inventory_source.inventory.read_role.members.add(rando)
        delete(
            reverse(
                'api:inventory_source_hosts_list',
                kwargs={'version': 'v2', 'pk': inventory_source.pk}
            ), user=rando, expect=403
        )

    def test_sublist_delete_functionality(self, inventory_source, host, rando, delete):
        inventory_source.hosts.add(host)
        inventory_source.inventory.admin_role.members.add(rando)
        delete(
            reverse(
                'api:inventory_source_hosts_list',
                kwargs={'version': 'v2', 'pk': inventory_source.pk}
            ), user=rando, expect=204
        )
        assert inventory_source.hosts.count() == 0

    def test_destroy_permission_check(self, job_factory, system_auditor, delete):
        job = job_factory()
        resp = delete(
            job.get_absolute_url(), user=system_auditor
        )
        assert resp.status_code == 403


@pytest.mark.django_db
def test_non_filterable_field(options, instance, admin_user):
    r = options(
        url=instance.get_absolute_url(),
        user=admin_user
    )
    field_info = r.data['actions']['GET']['percent_capacity_remaining']
    assert 'filterable' in field_info
