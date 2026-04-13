using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using GameUtility;
using GameUtility.IO;
using UnityEngine;

namespace Data.TableScript
{
    public static class ConfigManager
    {
        private static bool _isLoaded;
        private static readonly Dictionary<Type, IConfigDataBase> Data = new();
        private static Assembly _assembly;

        private const string AssemblyName = "RuntimeShared";
        private const string NamespaceName = "Data.TableScript";
        public const string ConfigRawInfoSuffix = "Info";
        public const string ConfigDataBaseSuffix = "Config";

        /// <summary>
        /// 加载所有配置表，通常在开始游戏时执行
        /// </summary>
        /// <param name="reload">是否重新加载，通常只有debug时使用</param>
        /// <exception cref="Exception">加载失败</exception>
        /// <exception cref="InvalidOperationException">数据类没有继承IConfigDataBase接口</exception>
        public static void LoadAll(bool reload = false)
        {
            if (_isLoaded && !reload)
            {
                return;
            }

            try
            {
                _assembly = Assembly.Load(AssemblyName);
            }
            catch (FileNotFoundException)
            {
                throw;
            }
            catch (Exception ex)
            {
                throw new Exception($"加载程序集失败: {ex.Message}");
            }

            foreach (var type in _assembly.GetTypes())
            {
                if (!type.IsClass || type.IsAbstract || !typeof(IConfigDataBase).IsAssignableFrom(type))
                {
                    continue;
                }

                // 获取泛型参数类型（如果需要按类型存储）
                Type genericArg = null;
                var baseType = type.BaseType;
                if (baseType is { IsGenericType: true })
                {
                    genericArg = baseType.GetGenericArguments().FirstOrDefault();
                }

                if (Activator.CreateInstance(type) is IConfigDataBase instance)
                {
                    // 使用泛型参数类型作为字典 key，如果没有泛型参数，就用类类型本身
                    var key = genericArg ?? type;
                    if (!Data.ContainsKey(key))
                    {
                        instance.Load();
                        Data[key] = instance;
                    }
                }
                else
                {
                    throw new InvalidOperationException(
                        $"无法创建 {type.Name} 的实例，确保它实现了 IConfigDataBase 接口。");
                }
            }

            _isLoaded = true;
        }

        public static T DeserializeConfigData<T>(string fileName) where T : class
        {
            var filePath = AssetPath.GetConfigDataPath(fileName);
#if UNITY_EDITOR
            var result = JsonSerializeUtility.DeserializeFromFile<T>(filePath);
#else
            var jsonText = GameModule.Resource.LoadAsset<UnityEngine.TextAsset>(filePath);
            var result = Newtonsoft.Json.JsonConvert.DeserializeObject<T>(jsonText.text, GameUtility.IO.JsonSerializeUtility.ConfigDeserializeSettings);
            GameModule.Resource.UnloadAsset(jsonText);
#endif
            return result;
        }

        /// <summary>
        /// 加载指定的配置表，默认为重新加载
        /// </summary>
        /// <typeparam name="T">行数据类型，比如<see cref="ItemInfo"/></typeparam>
        /// <exception cref="InvalidOperationException">数据类没有继承IConfigDataBase</exception>
        public static void Load<T>(bool reload = true)
        {
            var type = typeof(T);
            Load(type, reload);
        }

        private static void Load(Type type, bool reload)
        {
            if (Data.ContainsKey(type) && !reload)
            {
                return;
            }

            var assembly = Assembly.Load(AssemblyName);
            var targetType = assembly.GetTypes();
            foreach (var t in targetType.Where(t => t.IsClass && !t.IsAbstract))
            {
                var baseType = t.BaseType;
                if (baseType is not { IsGenericType: true })
                    continue;

                // var genericTypeDef = baseType.GetGenericTypeDefinition();
                // if (genericTypeDef == null || genericTypeDef != typeof(ConfigDataBase<>) &&
                //     genericTypeDef != typeof(ConfigDataWithCompositeId<>) &&
                //     genericTypeDef != typeof(ConfigDataWithKey<>))
                //     continue;

                var genericArg = baseType.GetGenericArguments()[0];
                if (genericArg == type)
                {
                    if (Activator.CreateInstance(t) is IConfigDataBase instance)
                    {
                        instance.Load();
                        Data[genericArg] = instance;
                        return;
                    }

                    throw new InvalidOperationException(
                        $"无法创建 {t.Name} 的实例，确保它继承自 ConfigDataBase<T> 并实现了 IConfigDataBase 接口。");
                }
            }
        }

        /// <summary>
        /// 获取某个配置表的显示映射字典，key是唯一id，value是用于显示的字符串
        /// 主要用于编辑器下的下拉列表显示
        /// </summary>
        /// <param name="type">配置表数据类类型</param>
        /// <returns>所有行数据的id和显式内容</returns>
        public static Dictionary<int, string> GetDisplayMap(Type type)
        {
            if (!Data.ContainsKey(type))
            {
                Load(type, true);
            }

            return Data[type].GetDisplayMap();
        }

        /// <summary>
        /// 通过唯一id查找数据
        /// </summary>
        /// <param name="id">唯一主键</param>
        /// <typeparam name="T">行数据类型，比如<see cref="ItemInfo"/></typeparam>
        /// <returns>id对应的行数据</returns>
        /// <exception cref="InvalidOperationException">无法找到对应id的数据</exception>
        public static T GetData<T>(int id) where T : IConfigRawInfo
        {
            var key = typeof(T);
            if (TryGetData(key, id, out var result))
            {
                return (T)result;
            }

            throw new InvalidOperationException($"Cannot find the config data of type {key.Name} by id: {id}.");
        }

        /// <summary>
        /// 尝试通过唯一id查找数据
        /// </summary>
        /// <param name="id">唯一主键</param>
        /// <param name="type">配置表数据类类型</param>
        ///  <param name="result">配置表数据结果</param>
        /// <returns>id对应的行数据</returns>
        /// <exception cref="InvalidOperationException">无法找到对应id的数据</exception>
        public static bool TryGetData(Type type, int id, out IConfigRawInfo result)
        {
            if (!Data.TryGetValue(type, out var typeData))
            {
                Load(type, true);
                typeData = Data[type];
            }

            return typeData.TryGetData(id, out result);
        }

        public static bool TryGetData<T>(int id, out T result) where T : IConfigRawInfo
        {
            var type = typeof(T);
            if (TryGetData(type, id, out var data))
            {
                result = (T)data;
                return true;
            }

            Debug.LogError($"不存在id为{id}的{type}配置表数据");
            result = default;
            return false;
        }

        /// <summary>
        /// 通过枚举类型的key查找数据，需要表格数据配置字符串作为主键，会自动转换为枚举
        /// </summary>
        /// <param name="key">跟字符串主键一致的枚举项</param>
        /// <typeparam name="T">行数据类型，比如<see cref="CombatAttributeInfo"/></typeparam>
        /// <returns></returns>
        /// <exception cref="InvalidOperationException"></exception>
        public static T GetDataByKey<T>(Enum key) where T : IConfigRawInfo
        {
            var typeKey = typeof(T);
            if (!Data.TryGetValue(typeKey, out var typeData))
            {
                Load<T>();
                typeData = Data[typeKey];
            }

            if (typeData is IConfigDataWithKey<T> configDataWithKey)
            {
                return configDataWithKey.GetDataByKey(key);
            }

            throw new InvalidOperationException($"Cannot find the config data of type {typeKey.Name} by key: {key}.");
        }

        /// <summary>
        /// 通过组合主键查找数据，需要表格数据配置key1和key2。
        /// </summary>
        /// <param name="key1">组合键1</param>
        /// <param name="key2">组合键2</param>
        /// <typeparam name="T">行数据类型，比如<see cref="LootInfo"/></typeparam>
        /// <returns>满足key1和key2的唯一行数据</returns>
        /// <exception cref="InvalidOperationException">无法找到满足条件的数据</exception>
        public static T GetDataByCompositeKey<T>(int key1, int key2) where T : IConfigRawInfo
        {
            var typeKey = typeof(T);
            if (Data.TryGetValue(typeKey, out var typeData))
            {
                if (typeData is ConfigDataWithCompositeId<T> configDataWithCompositeId)
                {
                    return configDataWithCompositeId.GetDataByCompositeKey(key1, key2);
                }
            }

            throw new InvalidOperationException(
                $"Cannot find the config data of type {typeKey.Name} by composite key: ({key1}, {key2}).");
        }

        /// <summary>
        /// 获取指定配置表的所有数据行
        /// </summary>
        /// <typeparam name="T">行数据类型，比如<see cref="LootInfo"/></typeparam>
        /// <returns>所有的行数据列表</returns>
        public static List<T> GetAllData<T>() where T : IConfigRawInfo
        {
            if (Data.TryGetValue(typeof(T), out var data) && data is IConfigDataBase<T> configData)
            {
                return configData.GetAllData();
            }

            return new List<T>();
        }

        /// <summary>
        /// 选择某个字段，返回所有行该字段的集合。比如选择所有角色表中的角色名字
        /// </summary>
        /// <param name="selector">筛选条件</param>
        /// <typeparam name="T">行数据类型，比如<see cref="ItemInfo"/></typeparam>
        /// <typeparam name="TResult">所选的字段类型，可以通过参数自动推断</typeparam>
        /// <returns>多行的该字段所对应数据机核</returns>
        /// <exception cref="InvalidOperationException">无法找到符合条件的数据</exception>
        public static IEnumerable<TResult> SelectCollection<T, TResult>(Func<T, TResult> selector)
            where T : IConfigRawInfo
        {
            var key = typeof(T);
            if (Data.TryGetValue(key, out var typeData))
            {
                // 转换：接口需要 Func<IConfigRawInfo, TResult>
                return typeData.SelectValueCollection(x => selector((T)x));
            }

            throw new InvalidOperationException($"Cannot find the config data of type {key.Name}.");
        }

        /// <summary>
        /// 获取满足条件的多行数据
        /// </summary>
        /// <param name="predicate">筛选条件委托</param>
        /// <typeparam name="T">行数据类型，比如<see cref="ItemInfo"/></typeparam>
        /// <returns>所有满足条件的行数据</returns>
        /// <exception cref="InvalidOperationException">无法找到符合条件的数据</exception>
        public static IEnumerable<T> GetCollection<T>(Func<T, bool> predicate) where T : IConfigRawInfo
        {
            var key = typeof(T);
            if (Data.TryGetValue(key, out var typeData))
            {
                // typeData.GetCollection 返回 IEnumerable<IConfigRawInfo>，再 Cast<T>()
                return typeData.GetCollection(x => predicate((T)x)).Cast<T>();
            }

            throw new InvalidOperationException($"Cannot find the config data of type {key.Name}.");
        }

        /// <summary>
        /// 获取指定名称的配置表行数据类型，例如传入"Item"返回<see cref="ItemInfo"/>类型
        /// </summary>
        /// <param name="configName">无后缀的配置表名</param>
        /// <returns>配置表行数据类型</returns>
        public static Type GetConfigRawInfoType(string configName)
        {
            if (_assembly == null)
            {
                _assembly = Assembly.Load(AssemblyName);
            }

            return _assembly.GetType($"{NamespaceName}.{configName}{ConfigRawInfoSuffix}");
        }
    }
}