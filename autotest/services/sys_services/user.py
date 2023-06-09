import traceback
import uuid
from typing import Dict, Union, Any, Text

from flask import request
from loguru import logger

from autotest.corelibs.bredis import br
from autotest.exc import codes
from autotest.exc.consts import TEST_USER_INFO, CACHE_DAY
from autotest.exc.partner_message import partner_errmsg
from autotest.models.sys_models import User, Menu, Roles
from autotest.serialize.sys_serializes.menu import MenuListSchema
from autotest.serialize.sys_serializes.user import (UserListSchema, UserRegisterSchema, UserQuery)
from autotest.services.sys_services.menu import MenuService
from autotest.utils.api import parse_pagination
from autotest.utils.des import encrypt_rsa_password, decrypt_rsa_password


class UserService:
    """用户类"""

    @staticmethod
    def login(**kwargs: Any) -> Dict[Text, Any]:
        """
        登录
        :return:
        """
        username = kwargs.get('username', None)
        logger.info("登录用户名：", username)
        password = kwargs.get('password', None)
        if not username and not password:
            raise ValueError(partner_errmsg.get(codes.PARTNER_CODE_PARAMS_FAIL))
        user_info = User.get_user_by_name(username)
        
        if not user_info:
            raise ValueError(partner_errmsg.get(codes.WRONG_USER_NAME_OR_PASSWORD))
        u_password = decrypt_rsa_password(user_info.password)

        if u_password != password:
            raise ValueError(partner_errmsg.get(codes.WRONG_USER_NAME_OR_PASSWORD))
        token = str(uuid.uuid4())
        # 用户信息
        user = UserListSchema().dump(user_info)
        result = user
        result['token'] = token
        # 菜单权限
        roles = Roles.get_roles_by_ids(user['roles'])
        menu_ids = []
        if roles:
            for i in roles:
                menu_ids += list(map(int, i.menus.split(',')))
        # 前端角色报错只保存子节点数据，所有这里要做处理，把父级菜单也返回给前端
        parent_ids = Menu.get_parent_id_by_ids(set(menu_ids))
        menu_ids += [i.parent_id for i in parent_ids]
        all_menu = MenuListSchema().dump(Menu.get_menu_by_ids(set(menu_ids)), many=True)
        parent_menu = [menu for menu in all_menu if menu['parent_id'] == 0]
        result['menus'] = MenuService.menu_assembly(parent_menu, all_menu) if menu_ids else []
        result['roles'] = ['all']

        br.set(TEST_USER_INFO.format(token), result, CACHE_DAY)
        logger.info('用户 [{}] 登录了系统'.format(user_info.username))
        return result

    @staticmethod
    def logout():
        """
        登出
        :return:
        """
        token = request.headers.get('token')
        try:
            br.delete(TEST_USER_INFO.format(token))
        except Exception as err:
            logger.error(traceback.format_exc())

    @staticmethod
    def user_register( **kwargs: Any) -> "User":
        """用户注册"""
        try:
            user_data = UserRegisterSchema().load(kwargs)
            print(user_data)
            user_info = User.get_user_by_name(user_data.get('username'))
            if user_info:
                raise ValueError(partner_errmsg.get(codes.USERNAME_OR_EMAIL_IS_REGISTER))
            user = User().update(**user_data)
            return user
        except Exception as err:
            logger.error(traceback.format_exc())
            raise ValueError(err)

    @staticmethod
    def list(**kwargs: Any) -> Dict[Text, Any]:
        """
        获取用户列表
        :param kwargs:  查询参数
        :return:
        """
        query_data = UserQuery().load(kwargs)
        data = parse_pagination(User.get_all_user(**query_data))
        _result, pagination = data.get('result'), data.get('pagination')
        _result = UserListSchema().dump(_result, many=True)
        result = {
            'rows': _result
        }
        result.update(pagination)
        return result

    @staticmethod
    def save_or_update(**kwargs: Any) -> "User":
        """
        用户保存方法
        :param kwargs: 用户字段
        :return:
        """
        user = User.get(kwargs.get('id')) if kwargs.get('id', None) else User()
        if not user.id:
            if User.get_user_by_name(kwargs.get('username')):
                raise ValueError('用户名以存在！')
            user = User()
        kwargs['password'] = encrypt_rsa_password('Aa123456')
        if kwargs.get('roles', None):
            kwargs['roles'] = ','.join(list(map(str, kwargs['roles'])))
        user.update(**kwargs)
        return user

    @staticmethod
    def deleted(id: Union[str, int]):
        """
        删除用户
        :param kwargs:
        :return:
        """
        try:
            user = User.get(id)
            user.delete() if user else ...
        except Exception as err:
            logger.error(traceback.format_exc())

    @staticmethod
    def check_token(token: str) -> Dict[Text, Any]:
        """
        校验token
        :param token: token
        :return:
        """
        user_info = br.get(TEST_USER_INFO.format(token))
        if not user_info:
            raise ValueError(partner_errmsg.get(codes.PARTNER_CODE_TOKEN_EXPIRED_FAIL))

        user_info = {
            'id': user_info.get('id', None),
            'username': user_info.get('username', None)
        }
        return user_info

    @staticmethod
    def change_password(**kwargs: Any) -> "User":
        """修改密码"""
        user_id = kwargs.get('user_id', None)
        old_pwd = kwargs.get('old_pwd', None)
        new_pwd = kwargs.get('new_pwd', None)
        re_new_pwd = kwargs.get('re_new_pwd', None)
        if not user_id:
            raise ValueError(partner_errmsg.get(codes.USER_ID_IS_NULL))
        if new_pwd != re_new_pwd:
            raise ValueError(partner_errmsg.get(codes.PASSWORD_TWICE_IS_NOT_AGREEMENT))
        user_info = User.get(user_id)
        pwd = decrypt_rsa_password(user_info.password)
        if new_pwd == pwd:
            raise ValueError(partner_errmsg.get(codes.NEW_PWD_NO_OLD_PWD_EQUAL))
        if old_pwd != pwd:
            raise ValueError(partner_errmsg.get(codes.OLD_PASSWORD_ERROR))
        new_pwd = encrypt_rsa_password(new_pwd)
        user_info.password = new_pwd
        user_info.save()
        return user_info

    @staticmethod
    def get_user_info_by_token(token: str) -> Dict[Text, Any]:
        """根据token获取用户信息"""
        user_info = br.get(TEST_USER_INFO.format(token))
        return user_info
