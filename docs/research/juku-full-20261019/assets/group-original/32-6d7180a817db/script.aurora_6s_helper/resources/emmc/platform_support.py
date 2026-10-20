"""Match mutually consistent CoreELEC release aliases, including NG's arm userspace."""
def branch(release):
    variants = {release[k] for k in ('DISTRO_DEVICE','COREELEC_DEVICE') if release.get(k)}
    variants.update(release[k].split('.')[0] for k in ('DISTRO_ARCH','COREELEC_ARCH','LIBREELEC_ARCH') if release.get(k))
    if release.get('ID') != 'coreelec' or len(variants) != 1:
        raise ValueError('无法明确识别 CoreELEC 分支，或系统信息存在冲突')
    value=variants.pop()
    if (value,release.get('VERSION_ID','').split('.')[0]) not in (('Amlogic-no','22'),('Amlogic-ng','21')):
        raise ValueError('eMMC 功能支持 CoreELEC NO 22.x / NG 21.x（NG 测试中）')
    return value
