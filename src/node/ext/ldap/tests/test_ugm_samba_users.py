from node.tests import NodeTestCase
from node.ext.ldap import testing
from node.ext.ldap.ugm import Ugm


class TestUGMSambaUsers(NodeTestCase):
    layer = testing.LDIF_sambaUsers

    def test_samba_users(self):
        ucfg = self.layer['ucfg']
        gcfg = self.layer['gcfg']
        props = self.layer['props']

        ugm = Ugm(props=props, ucfg=ucfg, gcfg=gcfg)
        self.assertEqual(
            ugm.users.search(),
            [u'uid0', u'uid1', u'uid2']
        )
        self.assertEqual(
            ugm.users['uid0'].context.attrs['userPassword'],
            u'secret0'
        )
        self.assertEqual(
            ugm.users['uid0'].context.attrs['sambaLMPassword'],
            u'FF3750BCC2B22412AAD3B435B51404EE'
        )
        self.assertEqual(
            ugm.users['uid0'].context.attrs['sambaNTPassword'],
            u'62CF067F093CD75BBAA5D49E04689ED7'
        )
        ugm.users['uid0'].passwd('secret0', 'newsecret')
        password = ugm.users['uid0'].context.attrs['userPassword']
        self.assertTrue(password.startswith('{SSHA}'))
        self.assertEqual(
            ugm.users['uid0'].context.attrs['sambaLMPassword'],
            u'DB6574A2642D294B9A0F5D12D8F612D0'
        )
        self.assertEqual(
            ugm.users['uid0'].context.attrs['sambaNTPassword'],
            u'58D9F1588236EE9D4ED739E89FFCA25B'
        )
