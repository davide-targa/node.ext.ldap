# -*- coding: utf-8 -*-
from node.base import BaseNode
from node.ext.ldap import LDAPNode
from node.ext.ldap import ONELEVEL
from node.ext.ldap import testing
from node.ext.ldap.filter import LDAPFilter
from node.ext.ldap.ugm import Group
from node.ext.ldap.ugm import Groups
from node.ext.ldap.ugm import GroupsConfig
from node.ext.ldap.ugm import RolesConfig
from node.ext.ldap.ugm import Ugm
from node.ext.ldap.ugm import User
from node.ext.ldap.ugm import Users
from node.ext.ldap.ugm import UsersConfig
from node.ext.ldap.ugm._api import member_attribute
from node.ext.ldap.ugm._api import member_format
from node.ext.ldap.ugm._api import PrincipalAliasedAttributes
from node.tests import NodeTestCase


layer = testing.LDIF_principals
gcfg = GroupsConfig(
    baseDN='dc=my-domain,dc=com',
    attrmap={
        'id': 'cn',
        'rdn': 'cn'
    },
    scope=ONELEVEL,
    queryFilter='(objectClass=groupOfNames)',
    objectClasses=['groupOfNames']
)


class TestUGMPrincipals(NodeTestCase):
    layer = layer

    def test_user_basics(self):
        props = testing.props
        ucfg = testing.ucfg

        # Create a LDAPUsers node and configure it. In addition to the key
        # attribute, the login attribute also needs to be unique, which will
        # be checked upon calling ids() the first time
        self.assertEqual(ucfg.attrmap, {
            'telephoneNumber': 'telephoneNumber',
            'login': 'cn',
            'rdn': 'ou',
            'id': 'sn',
            'sn': 'sn'
        })

        # Query all user ids. Set ``cn`` as login attribute. In this case,
        # values are unique and therefore suitable as login attr
        users = Users(props, ucfg)
        self.assertEqual(
            users.ids,
            [u'Meier', u'M\xfcller', u'Schmidt', u'Umhauer']
        )

        # Principals idbydn
        self.assertEqual(
            users.idbydn('cn=user3,ou=customers,dc=my-domain,dc=com'),
            'Schmidt'
        )
        self.assertEqual(
            users.idbydn('cN=user3, ou=customers,dc=MY-domain,dc= com'),
            'Schmidt'
        )

        err = self.expect_error(
            KeyError,
            users.idbydn,
            'cN=inexistent, ou=customers,dc=MY-domain,dc= com'
        )
        self.assertEqual(
            str(err),
            "'cN=inexistent, ou=customers,dc=MY-domain,dc= com'"
        )

        # Get a user by id (utf-8 or unicode)
        mueller = users[u'Müller']
        self.assertTrue(isinstance(mueller, User))
        self.assertTrue(mueller is users[u'Müller'])

        # The real LDAP node is on ``context``
        self.assertEqual(
            repr(mueller.context),
            '<cn=user2,ou=customers,dc=my-domain,dc=com:cn=user2 - False>'
        )

        # The '?' is just ``__repr__`` going to ascii, the id is in proper unicode
        self.check_output("<User object 'M?ller' at ...>", repr(mueller))
        self.assertEqual(mueller.id, u'Müller')

        # A user has a login
        self.assertEqual(mueller.login, 'user2')

        # And attributes
        self.assertTrue(isinstance(mueller.attrs, PrincipalAliasedAttributes))
        context_attrs = sorted(mueller.attrs.context.items())
        self.assertEqual(context_attrs[:-1], [
            (u'cn', u'user2'),
            (u'objectClass', [u'top', u'person']),
            (u'sn', u'Müller'),
            (u'telephoneNumber', u'1234')
        ])
        self.assertEqual(context_attrs[-1][0], u'userPassword')
        self.assertEqual(sorted(mueller.attrs.items()), [
            ('id', u'Müller'),
            ('login', u'user2'),
            ('telephoneNumber', u'1234')
        ])

        # Query all user nodes
        self.check_output("""
        [<User object 'Meier' at ...>,
        <User object 'M?ller' at ...>,
        <User object 'Schmidt' at ...>,
        <User object 'Umhauer' at ...>]
        """, str([users[id] for id in sorted(users.keys())]))

        self.assertEqual([repr(users[id].context) for id in sorted(users.keys())], [
            '<cn=user1,dc=my-domain,dc=com:cn=user1 - False>',
            '<cn=user2,ou=customers,dc=my-domain,dc=com:cn=user2 - False>',
            '<cn=user3,ou=customers,dc=my-domain,dc=com:cn=user3 - False>',
            '<cn=n?sty\, User,ou=customers,dc=my-domain,dc=com:cn=n?sty\, User - False>'
        ])

    def test_authentication(self):
        props = testing.props
        ucfg = testing.ucfg
        users = Users(props, ucfg)
        mueller = users[u'Müller']

        # Authenticate a user, via the user object. (also see 'via LDAPUsers'
        # below, after passwd, this is to make sure, that LDAPUsers.authenticate
        # does not work on a cached copy)
        self.assertTrue(mueller.authenticate('foo2'))
        self.assertFalse(mueller.authenticate('bar'))

        # Change a users password, supplying the old password, via the user object
        oldpw = 'foo2'
        newpw = 'new'
        mueller.passwd(oldpw, newpw)
        self.assertFalse(mueller.authenticate('foo2'))
        self.assertTrue(mueller.authenticate('new'))

        # And via LDAPUsers::
        oldpw = newpw
        newpw = 'newer'
        users.passwd(mueller.id, oldpw, newpw)

        # Authenticate a user via LDAPUsers, either by id or by login, but not
        # both. The id is returned if sucessful, otherwise None
        self.assertFalse(users.authenticate('wrong', 'creds'))
        self.assertEqual(users.authenticate(mueller.login, 'newer'), u'Müller')
        self.assertFalse(users.authenticate(id='wrong', pw='cresd'))
        self.assertFalse(users.authenticate(id=mueller.id, pw='bar'))
        self.assertEqual(users.authenticate(id=mueller.id, pw='newer'), u'Müller')

    def test_create_user(self):
        # Create new User. Provide some user defaults in user configuration.
        # A default is either the desired value or a callback accepting the
        # principals node and the id and returns the desired value.
        def telephoneNumberDefault(node, id):
            # default value callback function
            return '123'

        props = testing.props
        add_ucfg = UsersConfig(
            baseDN='ou=customers,dc=my-domain,dc=com',
            attrmap={
                'id': 'sn',
                'login': 'cn',
                'rdn': 'cn',
                'telephoneNumber': 'telephoneNumber',
                'sn': 'sn',
            },
            scope=ONELEVEL,
            queryFilter='(objectClass=person)',
            objectClasses=['top', 'person'],
            defaults={
                'sn': 'Surname',
                'telephoneNumber': telephoneNumberDefault,
            },
        )
        users = Users(props, add_ucfg)

        self.assertEqual(
            sorted(users.ids),
            [u'M\xfcller', u'Schmidt', u'Umhauer', u'sn_binary']
        )

        user = users.create(
            'newid',
            login='newcn',
            id='ID Ignored',  # gets ignored, id is taken from pid arg
            sn='Surname Ignored'  # gets ignored, id maps to sn, thus id rules
        )
        self.assertTrue(isinstance(user, User))

        self.assertEqual(
            repr(user.context),
            '<cn=newcn,ou=customers,dc=my-domain,dc=com:cn=newcn - True>'
        )

        self.assertEqual(sorted(user.attrs.items()), [
            ('id', u'newid'),
            ('login', u'newcn'),
            ('telephoneNumber', u'123')
        ])

        self.assertEqual(sorted(user.context.attrs.items()), [
            (u'cn', u'newcn'),
            (u'objectClass', [u'top', u'person']),
            (u'sn', u'newid'),
            (u'telephoneNumber', u'123')
        ])

        self.assertEqual(
            sorted(users.ids),
            [u'Müller', u'Schmidt', u'Umhauer', u'newid', u'sn_binary']
        )

        err = self.expect_error(
            KeyError,
            users.create,
            'newid'
        )
        self.assertEqual(str(err), 'u"Principal with id \'newid\' already exists."')

        err = self.expect_error(
            ValueError,
            users.__setitem__,
            'foo',
            BaseNode()
        )
        self.assertEqual(str(err), "Given value not instance of 'User'")

        self.assertEqual(
            repr(users['newid'].context),
            '<cn=newcn,ou=customers,dc=my-domain,dc=com:cn=newcn - True>'
        )

        # Persist and reload
        users()
        users.reload = True

        self.assertEqual(
            sorted(users.keys()),
            [u'Müller', u'Schmidt', u'Umhauer', u'newid', 'sn_binary'])

        self.assertEqual(
            repr(users['newid'].context),
            '<cn=newcn,ou=customers,dc=my-domain,dc=com:cn=newcn - False>'
        )

        # Delete User
        del users['newid']
        users.context()

    def test_search(self):
        props = testing.props
        ucfg = testing.ucfg
        users = Users(props, ucfg)

        # Search for users
        schmidt = users['Schmidt']
        self.assertEqual(
            users.search(criteria=dict(sn=schmidt.attrs['sn']), exact_match=True),
            [u'Schmidt']
        )

        self.assertEqual(
            sorted(users.search()),
            [u'Meier', u'M\xfcller', u'Schmidt', u'Umhauer']
        )

        self.assertEqual(users.search(attrlist=['login']), [
            (u'Meier', {'login': [u'user1']}),
            (u'M\xfcller', {'login': [u'user2']}),
            (u'Schmidt', {'login': [u'user3']}),
            (u'Umhauer', {'login': [u'n\xe4sty, User']})
        ])

        self.assertEqual(
            users.search(criteria=dict(sn=schmidt.attrs['sn']), attrlist=['login']),
            [(u'Schmidt', {'login': [u'user3']})]
        )

        # By default, search function is paginated. To control the LDAP search
        # behavior in more detail, ``raw_search`` can be used
        results, cookie = users.raw_search(page_size=3, cookie='')
        self.assertEqual(results, [u'Meier', u'M\xfcller', u'Schmidt'])

        results, cookie = users.raw_search(page_size=3, cookie=cookie)
        self.assertEqual(results, [u'Umhauer'])
        self.assertEqual(cookie, '')

        # Only attributes defined in attrmap can be queried
        self.expect_error(
            KeyError,
            users.search,
            criteria=dict(sn=schmidt.attrs['sn']),
            attrlist=['description']
        )

        self.assertEqual(
            users.search(
                criteria=dict(sn=schmidt.attrs['sn']),
                attrlist=['telephoneNumber']
            ),
            [(u'Schmidt', {'telephoneNumber': [u'1234']})]
        )

        filter = LDAPFilter('(objectClass=person)')
        filter &= LDAPFilter('(!(objectClass=inetOrgPerson))')
        filter |= LDAPFilter('(objectClass=some)')

        # normally set via principals config
        original_search_filter = users.context.search_filter
        self.assertEqual(
            original_search_filter,
            '(&(objectClass=person)(!(objectClass=inetOrgPerson)))'
        )

        users.context.search_filter = filter
        self.assertEqual(
            users.search(),
            [u'Meier', u'M\xfcller', u'Schmidt', u'Umhauer']
        )

        filter = LDAPFilter('(objectClass=person)')
        filter &= LDAPFilter('(objectClass=some)')

        # normally set via principals config
        users.context.search_filter = filter
        self.assertEqual(users.search(), [])

        users.context.search_filter = original_search_filter

    def test_changed_flag(self):
        props = testing.props
        ucfg = testing.ucfg
        users = Users(props, ucfg)

        # The changed flag
        self.assertFalse(users.changed)
        self.check_output("""
        <class 'node.ext.ldap.ugm._api.Users'>: None
          <class 'node.ext.ldap.ugm._api.User'>: Meier
          <class 'node.ext.ldap.ugm._api.User'>: M?ller
          <class 'node.ext.ldap.ugm._api.User'>: Schmidt
          <class 'node.ext.ldap.ugm._api.User'>: Umhauer
        """, users.treerepr())

        self.assertEqual(
            repr(users[users.values()[1].name].context),
            '<cn=user2,ou=customers,dc=my-domain,dc=com:cn=user2 - False>'
        )

        self.check_output("""
        <dc=my-domain,dc=com - False>
          ...
            <cn=user2,ou=customers,dc=my-domain,dc=com:cn=user2 - False>
            <cn=user3,ou=customers,dc=my-domain,dc=com:cn=user3 - False>
            <cn=n?sty\, User,ou=customers,dc=my-domain,dc=com:cn=n?sty\, User - False>
          ...
          <cn=user1,dc=my-domain,dc=com:cn=user1 - False>
          ...
        """, users.context.treerepr())

        users['Meier'].attrs['telephoneNumber'] = '12345'
        self.assertTrue(users['Meier'].attrs.changed)
        self.assertTrue(users['Meier'].changed)
        self.assertTrue(users.changed)

        self.check_output("""
        <dc=my-domain,dc=com - True>
          ...
            <cn=user2,ou=customers,dc=my-domain,dc=com:cn=user2 - False>
            <cn=user3,ou=customers,dc=my-domain,dc=com:cn=user3 - False>
            <cn=n?sty\, User,ou=customers,dc=my-domain,dc=com:cn=n?sty\, User - False>
          ...
          <cn=user1,dc=my-domain,dc=com:cn=user1 - True>
          ...
        """, users.context.treerepr())

        users['Meier'].attrs.context.load()
        self.assertFalse(users['Meier'].attrs.changed)
        self.assertFalse(users['Meier'].changed)
        self.assertFalse(users.changed)

        self.check_output("""
        <dc=my-domain,dc=com - False>
          ...
            <cn=user2,ou=customers,dc=my-domain,dc=com:cn=user2 - False>
            <cn=user3,ou=customers,dc=my-domain,dc=com:cn=user3 - False>
            <cn=n?sty\, User,ou=customers,dc=my-domain,dc=com:cn=n?sty\, User - False>
          ...
          <cn=user1,dc=my-domain,dc=com:cn=user1 - False>
          ...
        """, users.context.treerepr())

    def test_invalidate(self):
        props = testing.props
        ucfg = testing.ucfg
        users = Users(props, ucfg)

        # Make sure data is loaded and trees are initialized
        users.context.treerepr()
        users.treerepr()

        # Invalidate principals
        self.assertEqual(len(users.storage.keys()), 4)
        self.assertEqual(len(users.context.storage.keys()), 5)

        users.invalidate(u'Inexistent')
        self.assertEqual(len(users.storage.keys()), 4)
        self.assertEqual(len(users.context.storage.keys()), 5)
        self.assertEqual(
            sorted(users.storage.keys()),
            [u'Meier', u'Müller', u'Schmidt', u'Umhauer']
        )

        user_container = users[u'Schmidt'].context.parent.storage
        self.assertEqual(len(user_container.keys()), 7)

        users.invalidate(u'Schmidt')
        self.assertEqual(
            sorted(users.storage.keys()),
            [u'Meier', u'Müller', u'Umhauer']
        )

        self.assertEqual(len(user_container.keys()), 6)
        self.assertEqual(len(users.context.keys()), 5)

        users.invalidate()
        self.assertEqual(len(users.storage.keys()), 0)
        self.assertEqual(len(users.context.storage.keys()), 0)

    def test_group_basics(self):
        props = testing.props
        ucfg = testing.ucfg
        users = Users(props, ucfg)

        # A user does not know about it's groups if initialized directly
        err = self.expect_error(
            AttributeError,
            lambda: users['Meier'].groups
        )
        self.assertEqual(str(err), "'NoneType' object has no attribute 'groups'")

        # Create a LDAPGroups node and configure it
        groups = Groups(props, gcfg)

        self.assertEqual(groups.keys(), [u'group1', u'group2'])
        self.assertEqual(groups.ids, [u'group1', u'group2'])

        group = groups['group1']
        self.assertTrue(isinstance(group, Group))

        self.assertEqual(sorted(group.attrs.items()), [
            ('member', [
                u'cn=user3,ou=customers,dc=my-domain,dc=com',
                u'cn=user2,ou=customers,dc=my-domain,dc=com'
            ]),
            ('rdn', u'group1')
        ])

        self.assertEqual(sorted(group.attrs.context.items()), [
            (u'cn', u'group1'),
            (u'member', [
                u'cn=user3,ou=customers,dc=my-domain,dc=com',
                u'cn=user2,ou=customers,dc=my-domain,dc=com'
            ]),
            (u'objectClass', [u'top', u'groupOfNames'])
        ])

        self.assertEqual(
            groups.context.child_defaults,
            {'objectClass': ['groupOfNames']}
        )

    def test_add_group(self):
        props = testing.props
        groups = Groups(props, gcfg)

        group = groups.create('group3')
        self.assertEqual(sorted(group.attrs.items()), [
            ('member', ['cn=nobody']),
            ('rdn', u'group3')
        ])

        self.assertEqual(sorted(group.attrs.context.items()), [
            (u'cn', u'group3'),
            (u'member', ['cn=nobody']),
            (u'objectClass', [u'groupOfNames'])
        ])

        groups()
        self.assertEqual(groups.ids, [u'group1', u'group2', u'group3'])

        # XXX: dummy member should be created by default value callback,
        #      currently a __setitem__ plumbing on groups object

        res = groups.context.ldap_session.search(
            queryFilter='cn=group3',
            scope=ONELEVEL
        )
        self.assertEqual(res, [
            ('cn=group3,dc=my-domain,dc=com', {
                'member': ['cn=nobody'],
                'objectClass': ['groupOfNames'],
                'cn': ['group3']
            })
        ])

        # Delete create group
        del groups['group3']
        groups()

    def test_membership(self):
        props = testing.props
        groups = Groups(props, gcfg)

        # Directly created groups object have no access to it's refering users
        err = self.expect_error(
            AttributeError,
            lambda: groups['group1'].member_ids
        )
        self.assertEqual(str(err), "'NoneType' object has no attribute 'users'")

        # Currently, the member relation is computed hardcoded and maps to
        # object classes. This will propably change in future. Right now
        # 'posigGroup', 'groupOfUniqueNames', and 'groupOfNames' are supported
        self.assertEqual(member_format('groupOfUniqueNames'), 0)
        self.assertEqual(member_attribute('groupOfUniqueNames'), 'uniqueMember')

        self.assertEqual(member_format('groupOfNames'), 0)
        self.assertEqual(member_attribute('groupOfNames'), 'member')

        self.assertEqual(member_format('posixGroup'), 1)
        self.assertEqual(member_attribute('posixGroup'), 'memberUid')

        err = self.expect_error(Exception, member_format, 'foo')
        self.assertEqual(str(err), 'Unknown format')
        err = self.expect_error(Exception, member_attribute, 'foo')
        self.assertEqual(str(err), 'Unknown member attribute')

        self.assertEqual(groups['group1']._member_format, 0)
        self.assertEqual(groups['group1']._member_attribute, 'member')

        # Create a UGM object
        ucfg = layer['ucfg']
        ugm = Ugm(props=props, ucfg=ucfg, gcfg=gcfg)

        # Fetch users and groups
        self.assertTrue(isinstance(ugm.users, Users))
        self.assertTrue(isinstance(ugm.groups, Groups))

        self.assertEqual(ugm.groups._key_attr, 'cn')

        group_1 = ugm.groups['group1']
        self.assertEqual(len(group_1.users), 2)
        self.assertTrue(isinstance(group_1.users[0], User))
        self.assertEqual(
            sorted([it.name for it in group_1.users]),
            [u'Müller', u'Schmidt']
        )
        group_2 = ugm.groups['group2']
        self.assertEqual([it.name for it in group_2.users], [u'Umhauer'])

        schmidt = ugm.users['Schmidt']
        self.assertEqual(schmidt.group_ids, [u'group1'])
        self.assertEqual(len(schmidt.groups), 1)
        self.assertTrue(isinstance(schmidt.groups[0], Group))
        self.assertEqual([it.name for it in schmidt.groups], [u'group1'])

        # Add and remove user from group
        group = ugm.groups['group1']
        self.assertEqual(group.member_ids, [u'Schmidt', u'M\xfcller'])
        self.assertEqual(
            group.translate_key('Umhauer'),
            u'cn=n\xe4sty\\, User,ou=customers,dc=my-domain,dc=com'
        )

        group.add('Umhauer')
        self.assertEqual(sorted(group.attrs.items()), [
            ('member', [
                u'cn=user3,ou=customers,dc=my-domain,dc=com',
                u'cn=user2,ou=customers,dc=my-domain,dc=com',
                u'cn=n\xe4sty\\, User,ou=customers,dc=my-domain,dc=com'
            ]),
            ('rdn', u'group1')
        ])
        self.assertEqual(
            group.member_ids,
            [u'Schmidt', u'M\xfcller', u'Umhauer']
        )
        group()

        del group['Umhauer']
        self.assertEqual(group.member_ids, [u'Schmidt', u'M\xfcller'])

        # Delete Group
        groups = ugm.groups
        group = groups.create('group3')
        group.add('Schmidt')
        groups()

        self.assertEqual(
            groups.keys(),
            [u'group1', u'group2', u'group3']
        )
        self.assertEqual(len(groups.values()), 3)
        self.assertTrue(isinstance(groups.values()[0], Group))
        self.assertEqual(
            [it.name for it in groups.values()],
            [u'group1', u'group2', u'group3']
        )
        self.assertEqual(
            [it.name for it in ugm.users['Schmidt'].groups],
            [u'group1', u'group3']
        )
        self.assertEqual(group.member_ids, [u'Schmidt'])

        del groups['group3']
        groups()

        self.assertEqual(groups.keys(), [u'group1', u'group2'])
        self.assertEqual(ugm.users['Schmidt'].group_ids, ['group1'])

"""
Test role mappings. Create container for roles.::

    >>> node = LDAPNode('dc=my-domain,dc=com', props)
    >>> node['ou=roles'] = LDAPNode()
    >>> node['ou=roles'].attrs['objectClass'] = ['organizationalUnit']
    >>> node()

Test accessing unconfigured roles.::

    >>> ugm = Ugm(props=props, ucfg=ucfg, gcfg=gcfg, rcfg=None)
    >>> user = ugm.users['Meier']
    >>> ugm.roles(user)
    []

    >>> ugm.add_role('viewer', user)
    Traceback (most recent call last):
      ...
    ValueError: Role support not configured properly

    >>> ugm.remove_role('viewer', user)
    Traceback (most recent call last):
      ...
    ValueError: Role support not configured properly

Configure role config represented by object class 'groupOfNames'::

    >>> rcfg = RolesConfig(
    ...     baseDN='ou=roles,dc=my-domain,dc=com',
    ...     attrmap={
    ...         'id': 'cn',
    ...         'rdn': 'cn',
    ...     },
    ...     scope=ONELEVEL,
    ...     queryFilter='(objectClass=groupOfNames)',
    ...     objectClasses=['groupOfNames'],
    ...     defaults={},
    ... )

    >>> ugm = Ugm(props=props, ucfg=ucfg, gcfg=gcfg, rcfg=rcfg)

    >>> roles = ugm._roles
    >>> roles
    <Roles object 'roles' at ...>

No roles yet.::

    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles

Test roles for users.::

    >>> user = ugm.users['Meier']
    >>> ugm.roles(user)
    []

Add role for user, role gets created if not exists.::

    >>> ugm.add_role('viewer', user)

    >>> roles.keys()
    [u'viewer']

    >>> role = roles[u'viewer']
    >>> role
    <Role object 'viewer' at ...>

    >>> role.member_ids
    [u'Meier']

    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.User'>: Meier

    >>> ugm.roles_storage()

Query roles for principal via ugm object.::

    >>> ugm.roles(user)
    ['viewer']

Query roles for principal directly.::

    >>> user.roles
    ['viewer']

Add some roles for 'Schmidt'.::

    >>> user = ugm.users['Schmidt']
    >>> user.add_role('viewer')
    >>> user.add_role('editor')

    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.User'>: Meier
        <class 'node.ext.ldap.ugm._api.User'>: Schmidt
      <class 'node.ext.ldap.ugm._api.Role'>: editor
        <class 'node.ext.ldap.ugm._api.User'>: Schmidt

    >>> user.roles
    ['viewer', 'editor']

    >>> ugm.roles_storage()

Remove role 'viewer'.::

    >>> ugm.remove_role('viewer', user)
    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.User'>: Meier
      <class 'node.ext.ldap.ugm._api.Role'>: editor
        <class 'node.ext.ldap.ugm._api.User'>: Schmidt

Remove role 'editor', No other principal left, remove role as well.::

    >>> user.remove_role('editor')

    >>> roles.storage.keys()
    ['viewer']

    >>> roles.context._deleted_children
    set([u'cn=editor'])

    >>> roles.keys()
    [u'viewer']

    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.User'>: Meier

    >>> ugm.roles_storage()

Test roles for group.::

    >>> group = ugm.groups['group1']
    >>> ugm.roles(group)
    []

    >>> ugm.add_role('viewer', group)
    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.User'>: Meier
        <class 'node.ext.ldap.ugm._api.Group'>: group1
          <class 'node.ext.ldap.ugm._api.User'>: M?ller
          <class 'node.ext.ldap.ugm._api.User'>: Schmidt

    >>> ugm.roles(group)
    ['viewer']

    >>> group.roles
    ['viewer']

    >>> group = ugm.groups['group3']
    >>> group.add_role('viewer')
    >>> group.add_role('editor')

    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.User'>: Meier
        <class 'node.ext.ldap.ugm._api.Group'>: group1
          <class 'node.ext.ldap.ugm._api.User'>: M?ller
          <class 'node.ext.ldap.ugm._api.User'>: Schmidt
        <class 'node.ext.ldap.ugm._api.Group'>: group3
      <class 'node.ext.ldap.ugm._api.Role'>: editor
        <class 'node.ext.ldap.ugm._api.Group'>: group3

    >>> ugm.roles_storage()

If role already granted, an error is raised.::

    >>> group.add_role('editor')
    Traceback (most recent call last):
      ...
    ValueError: Principal already has role 'editor'

    >>> group.roles
    ['viewer', 'editor']

    >>> ugm.remove_role('viewer', group)
    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.User'>: Meier
        <class 'node.ext.ldap.ugm._api.Group'>: group1
          <class 'node.ext.ldap.ugm._api.User'>: M?ller
          <class 'node.ext.ldap.ugm._api.User'>: Schmidt
      <class 'node.ext.ldap.ugm._api.Role'>: editor
        <class 'node.ext.ldap.ugm._api.Group'>: group3

    >>> group.remove_role('editor')
    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.User'>: Meier
        <class 'node.ext.ldap.ugm._api.Group'>: group1
          <class 'node.ext.ldap.ugm._api.User'>: M?ller
          <class 'node.ext.ldap.ugm._api.User'>: Schmidt

    >>> ugm.roles_storage()

If role not exists, an error is raised.::

    >>> group.remove_role('editor')
    Traceback (most recent call last):
      ...
    ValueError: Role not exists 'editor'

If role is not granted, an error is raised.::

    >>> group.remove_role('viewer')
    Traceback (most recent call last):
      ...
    ValueError: Principal does not has role 'viewer'

Roles return ``Role`` instances on ``__getitem__``::

    >>> role = roles['viewer']
    >>> role
    <Role object 'viewer' at ...>

Group keys are prefixed with 'group:'.::

    >>> role.member_ids
    [u'Meier', u'group:group1']

``__getitem__`` of ``Role`` returns ``User`` or ``Group`` instance, depending
on key.::

    >>> role['Meier']
    <User object 'Meier' at ...>

    >>> role['group:group1']
    <Group object 'group1' at ...>

A KeyError is raised when trying to access an inexistent role member.::

    >>> role['inexistent']
    Traceback (most recent call last):
      ...
    KeyError: u'inexistent'

A KeyError is raised when trying to delete an inexistent role member.::

    >>> del role['inexistent']
    Traceback (most recent call last):
      ...
    KeyError: u'inexistent'

Delete user and check if roles are removed.::

    >>> ugm.printtree()
    <class 'node.ext.ldap.ugm._api.Ugm'>: None
      <class 'node.ext.ldap.ugm._api.Users'>: users
        <class 'node.ext.ldap.ugm._api.User'>: Meier
        <class 'node.ext.ldap.ugm._api.User'>: M?ller
        <class 'node.ext.ldap.ugm._api.User'>: Schmidt
        <class 'node.ext.ldap.ugm._api.User'>: Umhauer
      <class 'node.ext.ldap.ugm._api.Groups'>: groups
        <class 'node.ext.ldap.ugm._api.Group'>: group1
          <class 'node.ext.ldap.ugm._api.User'>: M?ller
          <class 'node.ext.ldap.ugm._api.User'>: Schmidt
        <class 'node.ext.ldap.ugm._api.Group'>: group2
          <class 'node.ext.ldap.ugm._api.User'>: Umhauer
        <class 'node.ext.ldap.ugm._api.Group'>: group3

    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.User'>: Meier
        <class 'node.ext.ldap.ugm._api.Group'>: group1
          <class 'node.ext.ldap.ugm._api.User'>: M?ller
          <class 'node.ext.ldap.ugm._api.User'>: Schmidt

    >>> users = ugm.users
    >>> del users['Meier']
    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles
      <class 'node.ext.ldap.ugm._api.Role'>: viewer
        <class 'node.ext.ldap.ugm._api.Group'>: group1
          <class 'node.ext.ldap.ugm._api.User'>: M?ller
          <class 'node.ext.ldap.ugm._api.User'>: Schmidt

    >>> users.storage.keys()
    [u'Schmidt', u'M\xfcller', u'Umhauer']

    >>> users.keys()
    [u'M\xfcller', u'Schmidt', u'Umhauer']

    >>> users.printtree()
    <class 'node.ext.ldap.ugm._api.Users'>: users
      <class 'node.ext.ldap.ugm._api.User'>: M?ller
      <class 'node.ext.ldap.ugm._api.User'>: Schmidt
      <class 'node.ext.ldap.ugm._api.User'>: Umhauer

Delete group and check if roles are removed.::

    >>> del ugm.groups['group1']
    >>> roles.printtree()
    <class 'node.ext.ldap.ugm._api.Roles'>: roles

    >>> ugm.printtree()
    <class 'node.ext.ldap.ugm._api.Ugm'>: None
      <class 'node.ext.ldap.ugm._api.Users'>: users
        <class 'node.ext.ldap.ugm._api.User'>: M?ller
        <class 'node.ext.ldap.ugm._api.User'>: Schmidt
        <class 'node.ext.ldap.ugm._api.User'>: Umhauer
      <class 'node.ext.ldap.ugm._api.Groups'>: groups
        <class 'node.ext.ldap.ugm._api.Group'>: group2
          <class 'node.ext.ldap.ugm._api.User'>: Umhauer
        <class 'node.ext.ldap.ugm._api.Group'>: group3

    >>> ugm()

"""