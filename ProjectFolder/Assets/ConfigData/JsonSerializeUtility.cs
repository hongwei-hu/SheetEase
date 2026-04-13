using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace GameUtility.IO
{
    /// <summary>
    /// 允许 Dictionary&lt;int, T&gt; 的 JSON 中包含非整数键（如 "_meta"），反序列化时跳过这些键。
    /// </summary>
    internal sealed class IntKeyDictionaryConverter : JsonConverter
    {
        public override bool CanConvert(Type objectType)
        {
            return objectType.IsGenericType
                && objectType.GetGenericTypeDefinition() == typeof(Dictionary<,>)
                && objectType.GetGenericArguments()[0] == typeof(int);
        }

        public override object ReadJson(JsonReader reader, Type objectType, object existingValue, JsonSerializer serializer)
        {
            var valueType = objectType.GetGenericArguments()[1];
            var dict = (IDictionary)Activator.CreateInstance(objectType);
            var jo = JObject.Load(reader);
            foreach (var property in jo.Properties())
            {
                if (int.TryParse(property.Name, out int key))
                {
                    dict[key] = property.Value.ToObject(valueType, serializer);
                }
                // 跳过非整数键（如 "_meta"）
            }
            return dict;
        }

        public override void WriteJson(JsonWriter writer, object value, JsonSerializer serializer)
        {
            var dict = (IDictionary)value;
            writer.WriteStartObject();
            foreach (DictionaryEntry entry in dict)
            {
                writer.WritePropertyName(entry.Key.ToString());
                serializer.Serialize(writer, entry.Value);
            }
            writer.WriteEndObject();
        }
    }

    public static class JsonSerializeUtility
    {
        public static readonly JsonSerializerSettings ConfigDeserializeSettings = new JsonSerializerSettings
        {
            Converters = { new IntKeyDictionaryConverter() }
        };

        public static T DeserializeFromFile<T>(string fullPath)
        {
            if (!File.Exists(fullPath))
            {
                throw new FileNotFoundException($"无法找到文件：{fullPath}");
            }

            try
            {
                var jsonText = File.ReadAllText(fullPath);
                var result = JsonConvert.DeserializeObject<T>(jsonText, ConfigDeserializeSettings);
                return result;
            }
            catch (JsonSerializationException e)
            {
                throw new JsonSerializationException($"反序列化文件失败：{fullPath}", e);
            }
            catch (JsonException e)
            {
                throw new JsonException($"JSON格式错误：{fullPath}", e);
            }
            catch (Exception e)
            {
                throw new Exception($"发生未知错误：{fullPath}", e);
            }
        }

        public static void SerializeToFile<T>(string fullPath, T obj)
        {
            if (string.IsNullOrEmpty(fullPath))
            {
                Debug.LogError("尝试序列化的json文件路径为空");
                return;
            }

            if (obj == null)
            {
                Debug.LogError("尝试序列化的对象为空");
                return;
            }

            try
            {
                var setting = new JsonSerializerSettings
                {
                    Formatting = Formatting.Indented,
                    ReferenceLoopHandling = ReferenceLoopHandling.Ignore
                };
                
                var jsonText = JsonConvert.SerializeObject(obj, setting);
                File.WriteAllText(fullPath, jsonText);
                Debug.Log($"序列化数据保存成功：{fullPath}");
            }
            catch (JsonSerializationException e)
            {
                throw new JsonSerializationException($"序列化对象失败：{fullPath}", e);
            }
            catch (JsonException e)
            {
                throw new JsonException($"JSON格式错误：{fullPath}", e);
            }
            catch (Exception e)
            {
                throw new Exception($"发生未知错误：{fullPath}", e);
            }
        }
    }
}