from setuptools import setup

setup(
    name='github-backup',
    version='0.0.4',
    description='Backup GitHub Repos Locally using GitHub Access Tokens',
    url='https://github.com/djekl/docker-github-backup',
    author='djekl',
    install_requires=['requests'],
    scripts=['github-backup.py'],
    zip_safe=True
)
